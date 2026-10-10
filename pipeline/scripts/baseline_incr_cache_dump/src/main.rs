//! Decode INCR `batch_*/data.incr` and re-check recorded dependencies.
//!
//! Layout copied from INCR `4b8e5dd` `src/cache/mod.rs` and
//! `src/ops/data.rs`: bincode 2, little-endian, fixed-width integers.
//! `dependency::check_cache_valid` is mirrored, not called.

use std::collections::{HashMap, HashSet};
use std::env;
use std::fs::{self, File};
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::UNIX_EPOCH;

use bincode::{Decode, Encode};
use xxhash_rust::xxh3::Xxh3;

#[derive(Clone, Debug, Encode, Decode, PartialEq, Eq)]
enum DependencyKey {
    DoesNotExist,
    Timestamp(u128),
    Hash(u64),
}

#[derive(Clone, Debug, Encode, Decode)]
struct CacheData {
    exit_code: i32,
    read_dependencies: HashMap<PathBuf, DependencyKey>,
    write_outputs: HashSet<PathBuf>,
    compressed_output: bool,
}

fn bincode_config() -> impl bincode::config::Config {
    bincode::config::standard()
        .with_little_endian()
        .with_fixed_int_encoding()
}

fn hash_file(path: &Path) -> io::Result<u64> {
    let mut file = File::open(path)?;
    let mut hasher = Xxh3::new();
    let mut buf = [0u8; 65_536];
    loop {
        match file.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => hasher.update(&buf[..n]),
            Err(err) if err.kind() == io::ErrorKind::Interrupted => continue,
            Err(err) => return Err(err),
        }
    }
    Ok(hasher.digest())
}

fn mtime_micros(path: &Path) -> io::Result<Option<u128>> {
    let metadata = match fs::metadata(path) {
        Ok(metadata) => metadata,
        Err(err) if err.kind() == io::ErrorKind::PermissionDenied => return Ok(None),
        Err(err) => return Err(err),
    };
    let modified = metadata.modified()?;
    let micros = modified.duration_since(UNIX_EPOCH).map_err(io::Error::other)?.as_micros();
    Ok(Some(micros))
}

fn key_name(key: &DependencyKey) -> &'static str {
    match key {
        DependencyKey::DoesNotExist => "does_not_exist",
        DependencyKey::Timestamp(_) => "timestamp",
        DependencyKey::Hash(_) => "hash",
    }
}

fn recorded_value(key: &DependencyKey) -> String {
    match key {
        DependencyKey::DoesNotExist => "absent".to_string(),
        DependencyKey::Timestamp(timestamp) => timestamp.to_string(),
        DependencyKey::Hash(hash) => hash.to_string(),
    }
}

struct LiveCheck {
    matches: bool,
    live: String,
    detail: String,
}

fn check_one(path: &Path, key: &DependencyKey) -> LiveCheck {
    match key {
        DependencyKey::DoesNotExist => {
            let exists = path.exists();
            LiveCheck {
                matches: !exists,
                live: if exists { "present".to_string() } else { "absent".to_string() },
                detail: "path.exists()".to_string(),
            }
        }
        DependencyKey::Timestamp(timestamp) => match mtime_micros(path) {
            Ok(Some(live)) if path.is_file() => LiveCheck {
                matches: live == *timestamp,
                live: live.to_string(),
                detail: "mtime_micros".to_string(),
            },
            Ok(Some(live)) => LiveCheck {
                matches: false,
                live: live.to_string(),
                detail: "not a file".to_string(),
            },
            Ok(None) => LiveCheck {
                matches: false,
                live: "permission_denied".to_string(),
                detail: "metadata permission denied".to_string(),
            },
            Err(err) => LiveCheck {
                matches: false,
                live: format!("error:{err}"),
                detail: "metadata error".to_string(),
            },
        },
        DependencyKey::Hash(hash) => {
            if !path.is_file() {
                return LiveCheck {
                    matches: false,
                    live: "not_a_file".to_string(),
                    detail: "hash requires a file".to_string(),
                };
            }
            match hash_file(path) {
                Ok(live) => LiveCheck {
                    matches: live == *hash,
                    live: live.to_string(),
                    detail: "xxh3".to_string(),
                },
                Err(err) if err.kind() == io::ErrorKind::PermissionDenied => LiveCheck {
                    matches: false,
                    live: "permission_denied".to_string(),
                    detail: "open permission denied".to_string(),
                },
                Err(err) => LiveCheck {
                    matches: false,
                    live: format!("error:{err}"),
                    detail: "hash error".to_string(),
                },
            }
        }
    }
}

fn find_data_files(root: &Path) -> io::Result<Vec<PathBuf>> {
    let mut out = Vec::new();
    if !root.exists() {
        return Ok(out);
    }
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        for entry in fs::read_dir(&dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
            } else if path.file_name().and_then(|n| n.to_str()) == Some("data.incr") {
                out.push(path);
            }
        }
    }
    out.sort();
    Ok(out)
}

fn entry_json(data_path: &Path, data: &CacheData) -> serde_json::Value {
    let batch = data_path.parent().unwrap_or(data_path);
    let stdout_exists = batch.join("stdout.incr").is_file();
    let stderr_exists = batch.join("stderr.incr").is_file();
    let outputs_exist = batch.join("outputs").is_dir();
    let mut deps = Vec::new();
    let mut mismatches = Vec::new();
    for (path, key) in &data.read_dependencies {
        let live = check_one(path, key);
        let row = serde_json::json!({
            "path": path.display().to_string(),
            "kind": key_name(key),
            "recorded": recorded_value(key),
            "live": live.live,
            "match": live.matches,
            "detail": live.detail,
        });
        if !live.matches {
            mismatches.push(row.clone());
        }
        deps.push(row);
    }
    deps.sort_by(|a, b| a["path"].as_str().cmp(&b["path"].as_str()));
    mismatches.sort_by(|a, b| a["path"].as_str().cmp(&b["path"].as_str()));
    let mut writes: Vec<String> = data
        .write_outputs
        .iter()
        .map(|path| path.display().to_string())
        .collect();
    writes.sort();
    let deps_ok = mismatches.is_empty();
    let writes_ok = data.write_outputs.is_empty() || outputs_exist;
    let would_pass = stdout_exists && stderr_exists && deps_ok && writes_ok;
    serde_json::json!({
        "data_file": data_path.display().to_string(),
        "batch_dir": batch.display().to_string(),
        "exit_code": data.exit_code,
        "compressed_output": data.compressed_output,
        "stdout_incr": stdout_exists,
        "stderr_incr": stderr_exists,
        "outputs_dir": outputs_exist,
        "n_dependencies": deps.len(),
        "n_mismatches": mismatches.len(),
        "n_write_outputs": writes.len(),
        "would_pass": would_pass,
        "fail_reasons": {
            "missing_stdout_or_stderr": !(stdout_exists && stderr_exists),
            "dependency_mismatch": !deps_ok,
            "missing_outputs_dir": !writes_ok,
        },
        "write_outputs": writes,
        "mismatches": mismatches,
        "dependencies": deps,
    })
}

fn dump_cache(cache: &Path, out: &Path) -> io::Result<()> {
    let files = find_data_files(cache)?;
    let mut entries = Vec::new();
    let mut decode_errors = Vec::new();
    for path in &files {
        let bytes = fs::read(path)?;
        match bincode::decode_from_slice::<CacheData, _>(&bytes, bincode_config()) {
            Ok((data, consumed)) if consumed == bytes.len() => {
                entries.push(entry_json(path, &data));
            }
            Ok((_, consumed)) => {
                decode_errors.push(serde_json::json!({
                    "path": path.display().to_string(),
                    "error": format!("trailing bytes: consumed {consumed} of {}", bytes.len()),
                }));
            }
            Err(err) => {
                decode_errors.push(serde_json::json!({
                    "path": path.display().to_string(),
                    "error": err.to_string(),
                    "nbytes": bytes.len(),
                }));
            }
        }
    }
    let would_pass = !entries.is_empty()
        && decode_errors.is_empty()
        && entries.iter().all(|entry| entry["would_pass"] == true);
    let payload = serde_json::json!({
        "cache_dir": cache.display().to_string(),
        "n_data_files": files.len(),
        "would_pass": would_pass,
        "decode_errors": decode_errors,
        "entries": entries,
    });
    fs::write(out, serde_json::to_string_pretty(&payload).unwrap() + "\n")?;
    Ok(())
}

fn selfcheck(out: &Path) -> io::Result<()> {
    let mut deps = HashMap::new();
    deps.insert(PathBuf::from("/data/missing"), DependencyKey::DoesNotExist);
    deps.insert(PathBuf::from("/data/file"), DependencyKey::Timestamp(1_791_665_794_000_000));
    deps.insert(PathBuf::from("/data/both"), DependencyKey::Hash(42));
    let mut writes = HashSet::new();
    writes.insert(PathBuf::from("/data/both"));
    let data = CacheData {
        exit_code: 0,
        read_dependencies: deps,
        write_outputs: writes,
        compressed_output: false,
    };
    let bytes = bincode::encode_to_vec(&data, bincode_config()).map_err(io::Error::other)?;
    let (decoded, consumed) =
        bincode::decode_from_slice::<CacheData, _>(&bytes, bincode_config()).map_err(io::Error::other)?;
    if consumed != bytes.len() || decoded.exit_code != 0 || decoded.read_dependencies.len() != 3 {
        return Err(io::Error::other("selfcheck round-trip failed"));
    }
    let payload = serde_json::json!({
        "selfcheck": "pass",
        "nbytes": bytes.len(),
        "n_dependencies": decoded.read_dependencies.len(),
        "config": "bincode 2.0.1 little-endian fixed-int",
    });
    fs::write(out, serde_json::to_string_pretty(&payload).unwrap() + "\n")?;
    Ok(())
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().skip(1).collect();
    let result = if args.len() == 2 && args[0] == "--selfcheck" {
        selfcheck(Path::new(&args[1]))
    } else if args.len() == 2 {
        dump_cache(Path::new(&args[0]), Path::new(&args[1]))
    } else {
        eprintln!("usage: baseline_incr_cache_dump --selfcheck OUT | CACHE_DIR OUT");
        return ExitCode::from(2);
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            eprintln!("baseline_incr_cache_dump: {err}");
            ExitCode::from(1)
        }
    }
}
