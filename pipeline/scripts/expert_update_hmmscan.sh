#!/bin/sh
# Expert incremental hmmscan. No check and no audit.
# Usage: expert_update_hmmscan.sh OLD_HMM NEW_HMM OLD_TBL QUERIES OUT_PREFIX
#        expert_update_hmmscan.sh --plan   < candidates.tsv
# The batch grid is the same planner as TARE (startup 2000, press 84),
# so this file is longer than the 30-line sketch. Line count is disclosed
# in the result JSON.
set -eu
LC_ALL=C
export LC_ALL

DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
TAB=$(printf '\t')

plan() {
    awk -v mode=keys -f "$DIR/expert_batch.awk" \
        | sort -t "$TAB" -k1,1n -k2,2 -k3,3n \
        | awk -v mode=chunks -v startup=2000 -v press=84 -f "$DIR/expert_batch.awk"
}

if [ "${1:-}" = "--plan" ]; then
    plan
    exit 0
fi

if [ "$#" -ne 5 ]; then
    echo "usage: $0 OLD_HMM NEW_HMM OLD_TBL QUERIES OUT_PREFIX" >&2
    exit 2
fi

OLD=$1
NEW=$2
OLD_TBL=$3
QUERIES=$4
OUT=$5
CPU=${CPU:-2}
WORK=${WORK:?set WORK to a scratch directory}
HMMSCAN=${HMMSCAN:-hmmscan}
HMMFETCH=${HMMFETCH:-hmmfetch}
HMMPRESS=${HMMPRESS:-hmmpress}

rm -rf "$WORK/batches"
mkdir -p "$WORK/batches" "$(dirname "$OUT")"

materialize() {
    case "$1" in
        *.gz)
            dest="$WORK/$(basename "$1" .gz)"
            if [ ! -s "$dest" ]; then
                gzip -dc "$1" > "$dest"
            fi
            printf '%s\n' "$dest"
            ;;
        *)
            printf '%s\n' "$1"
            ;;
    esac
}

OLD_TXT=$(materialize "$OLD")
NEW_TXT=$(materialize "$NEW")

awk '
    /^NAME / { name = $2; ck = "" }
    /^CKSUM / { ck = $2 }
    /^\/\// && name != "" { print name, ck; name = ""; ck = "" }
' "$OLD_TXT" > "$WORK/old.ck"
awk '
    /^NAME / { name = $2; ck = "" }
    /^CKSUM / { ck = $2 }
    /^\/\// && name != "" { print name, ck; name = ""; ck = "" }
' "$NEW_TXT" > "$WORK/new.ck"

Z=$(wc -l < "$WORK/new.ck" | tr -d ' ')
awk 'NR==FNR { old[$1] = $2; next }
     { if (!($1 in old) || old[$1] != $2) print $1 }
' "$WORK/old.ck" "$WORK/new.ck" > "$WORK/changed.names"
awk 'NR==FNR { old[$1] = $2; next }
     ($1 in old) && old[$1] == $2 { print $1 }
' "$WORK/old.ck" "$WORK/new.ck" > "$WORK/stable.names"

if [ ! -f "${NEW_TXT}.ssi" ] && [ ! -f "${NEW_TXT}.h3m.ssi" ]; then
    "$HMMFETCH" --index "$NEW_TXT"
fi

: > "$WORK/disc.tbl"
: > "$WORK/disc.dom"
if [ -s "$WORK/changed.names" ]; then
    "$HMMFETCH" -o "$WORK/changed.hmm" -f "$NEW_TXT" "$WORK/changed.names"
    "$HMMPRESS" -f "$WORK/changed.hmm"
    if [ "${EXPERT_OMIT_Z:-0}" = "1" ]; then
        "$HMMSCAN" --cut_ga --noali --cpu "$CPU" \
            --tblout "$WORK/disc.tbl" --domtblout "$WORK/disc.dom" \
            -o /dev/null "$WORK/changed.hmm" "$QUERIES"
    else
        "$HMMSCAN" --cut_ga --noali --cpu "$CPU" -Z "$Z" \
            --tblout "$WORK/disc.tbl" --domtblout "$WORK/disc.dom" \
            -o /dev/null "$WORK/changed.hmm" "$QUERIES"
    fi
fi

awk '/^>/ { print n "\t" substr($1, 2); n++ }' "$QUERIES" > "$WORK/q.order"
awk 'NR==FNR { st[$1] = 1; next }
     $0 !~ /^#/ && NF > 2 && st[$1] { print $3 "\t" $1 }
' "$WORK/stable.names" "$OLD_TBL" > "$WORK/cand.pairs"
awk '$0 !~ /^#/ && NF > 2 { print $3 "\t" $1 }' "$WORK/disc.tbl" >> "$WORK/cand.pairs"

awk -F '\t' '
    NR == FNR { idx[$2] = $1; next }
    {
        q = $1; t = $2
        if (!(q in idx)) next
        key = q SUBSEP t
        if (key in seen) next
        seen[key] = 1
        list[q] = (q in list && list[q] != "") ? list[q] "," t : t
    }
    END { for (q in list) print idx[q] "\t" q "\t" list[q] }
' "$WORK/q.order" "$WORK/cand.pairs" > "$WORK/cand.tsv"

plan < "$WORK/cand.tsv" > "$WORK/plan.txt"
awk '/^>/ { print substr($1, 2) }' "$QUERIES" > "$WORK/q.ids"

if [ ! -s "$WORK/plan.txt" ]; then
    : > "$OUT.tbl"
    : > "$OUT.dom"
    exit 0
fi

awk -v dir="$WORK/batches" -F '\t' '
    { out = dir "/b" $1 ".ids"; print $2 > out }
' "$WORK/plan.txt"
# Default field separator. A tab-only split makes $1 the whole FASTA
# header, so the query id never matches the plan.
awk -v dir="$WORK/batches" '
    NR == FNR { batch[$2] = $1; next }
    /^>/ {
        id = substr($1, 2)
        dest = (id in batch) ? (dir "/b" batch[id] ".faa") : ""
    }
    dest != "" { print > dest }
' "$WORK/plan.txt" "$QUERIES"

awk -F '\t' 'NR == FNR { b[$2] = $1; next }
    { if ($1 in b) u[b[$1] SUBSEP $2] = 1 }
    END { for (k in u) { split(k, a, SUBSEP); print a[1] "\t" a[2] } }
' "$WORK/plan.txt" "$WORK/cand.pairs" > "$WORK/batch.targets"
awk '/^NAME / { print $2 }' "$NEW_TXT" > "$WORK/new.names"

batches=$(cut -f1 "$WORK/plan.txt" | sort -n -u)
for b in $batches; do
    awk -F '\t' -v b="$b" 'NR == FNR { if ($1 == b) want[$2] = 1; next } want[$1] { print }' \
        "$WORK/batch.targets" "$WORK/new.names" > "$WORK/batches/b${b}.names"
    "$HMMFETCH" -o "$WORK/batches/b${b}.hmm" -f "$NEW_TXT" "$WORK/batches/b${b}.names"
    "$HMMPRESS" -f "$WORK/batches/b${b}.hmm"
    if [ "${EXPERT_OMIT_Z:-0}" = "1" ]; then
        "$HMMSCAN" --cut_ga --noali --cpu "$CPU" \
            --tblout "$WORK/batches/b${b}.tbl" --domtblout "$WORK/batches/b${b}.dom" \
            -o /dev/null "$WORK/batches/b${b}.hmm" "$WORK/batches/b${b}.faa"
    else
        "$HMMSCAN" --cut_ga --noali --cpu "$CPU" -Z "$Z" \
            --tblout "$WORK/batches/b${b}.tbl" --domtblout "$WORK/batches/b${b}.dom" \
            -o /dev/null "$WORK/batches/b${b}.hmm" "$WORK/batches/b${b}.faa"
    fi
    rm -f "$WORK/batches/b${b}.hmm" "$WORK/batches/b${b}.hmm.h3m" \
        "$WORK/batches/b${b}.hmm.h3i" "$WORK/batches/b${b}.hmm.h3f" \
        "$WORK/batches/b${b}.hmm.h3p"
done

merge_one() {
    qcol=$1
    shift
    awk -v qcol="$qcol" '
        NR == FNR { order[++n] = $1; known[$1] = 1; next }
        $0 ~ /^#/ || NF == 0 { next }
        {
            q = $qcol
            if (!(q in known)) { bad++; next }
            body[q] = body[q] $0 "\n"
        }
        END {
            if (bad) exit 3
            for (i = 1; i <= n; i++) printf "%s", body[order[i]]
        }
    ' "$WORK/q.ids" "$@"
}

# shellcheck disable=SC2086
merge_one 3 "$WORK"/batches/b*.tbl > "$OUT.tbl"
merge_one 4 "$WORK"/batches/b*.dom > "$OUT.dom"
