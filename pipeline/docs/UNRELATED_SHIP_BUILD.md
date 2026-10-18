# Unrelated ship: pfscanV3 build stop

Written after the three approved downloads and before any pfscan process.
The pilot, the protocol, and the measured run were not started. CARC was
not contacted. No seed from `20261101`–`20261109` was used.

pfscanV3 did not ship. There is no correctness JSON.

## Downloads

Scratch `~/tmp/tare_a/`. Byte sizes match the approval request. The
archives are not in git.

| File | Bytes |
|---|---|
| `pftools3-v3.2.13.zip` | 44209720 |
| `prosite2026_02.tar.bz2` | 11287183 |
| `prosite2026_03.tar.bz2` | 11352723 |

The zip unpacks to `sib-swiss-pftools3-3c2e02f`. `CMakeLists.txt` and
`ChangeLog` both say version 3.2.12. The semantics review named tag
`v3.2.13` at `e35e503`. This build used the approved archive as
unpacked. No other source was fetched.

## Configure

Host `arm64`, Apple clang 17.0.0 (`clang-1700.4.4.1`), target
`arm64-apple-darwin27.0.0`, CMake 4.3.2. Command:

```
cmake -DCMAKE_BUILD_TYPE=Release -DUSE_AFFINITY=OFF ../sib-swiss-pftools3-3c2e02f
```

The first configure stopped inside `PROJECT(PFTOOLS Fortran C)`.
`/opt/homebrew/bin/gfortran` compiled the test and the link failed with
`ld: library 'System' not found`. A second configure set `SDKROOT` and
`LIBRARY_PATH` to `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/lib`.
Fortran and C then identified, and CMake printed
`Compilation on architecture arm64.`

The C flag test is unconditional (`CMakeLists.txt` lines 70–74):

```
CHECK_C_COMPILER_FLAG(-msse HANDLE_SSE)
IF(HANDLE_SSE)
    SET(CMAKE_C_SSE_FLAGS "-msse")
ELSE(HANDLE_SSE)
    MESSAGE(FATAL_ERROR "C compiler does not support SSE")
ENDIF(HANDLE_SSE)
```

`HANDLE_SSE` failed. The compiler line and the error are:

```
/usr/bin/cc -DHANDLE_SSE -arch arm64 -isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk -msse ...
clang: error: unsupported option '-msse' for target 'arm64-apple-darwin27.0.0'
```

CMake stopped with `C compiler does not support SSE`. The same file
then requires `-msse2` and `-msse4.1` (lines 76–94). Those tests did
not run. The heuristic and the alignment live in `src/C/sse2`,
`src/C/sse41`, and the SSE intrinsics in `src/C/include`
(`_mm_malloc`, `GetHeuristicVersion`). There is no other ISA in this
configure.

## What this stop means

The locked command needs this binary. It does not exist on this
machine. The PROSITE archives were not scanned. No contract was
inferred, and no control was run.

This is the build failure named in `UNRELATED_SHIP_SEMANTICS.md`. The
tool stays pfscanV3.
