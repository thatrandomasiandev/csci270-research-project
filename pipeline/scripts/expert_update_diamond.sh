#!/bin/sh
# Expert incremental DIAMOND blastp. No check. Exits 0 when the search
# finishes, including when the hits disagree with a full stock run.
# Usage: expert_update_diamond.sh OLD_FA NEW_FA OLD_M8 QUERIES OUT
set -eu
LC_ALL=C
export LC_ALL

if [ "$#" -ne 5 ]; then
    echo "usage: $0 OLD_FA NEW_FA OLD_M8 QUERIES OUT" >&2
    exit 2
fi

OLD=$1
NEW=$2
OLD_M8=$3
QUERIES=$4
OUT=$5
CPU=${CPU:-2}
WORK=${WORK:?set WORK to a scratch directory}
DIAMOND=${DIAMOND:-diamond}
DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
PINNED_LETTERS=209017843

mkdir -p "$WORK/batches" "$(dirname "$OUT")"

stream() {
    case "$1" in
        *.gz) gzip -dc "$1" ;;
        *) cat "$1" ;;
    esac
}

digest() {
    stream "$1" | perl -MDigest::MD5=md5_hex -ne '
        if (/^>/) {
            if (defined $id) { print $id, "\t", md5_hex($seq), "\n" }
            ($id) = /^>(\S+)/;
            $seq = "";
        } else {
            s/\s+//g;
            $seq .= $_;
        }
        END { if (defined $id) { print $id, "\t", md5_hex($seq), "\n" } }
    '
}

extract() {
    perl - "$1" "$2" "$3" <<'PERL'
use strict;
use warnings;
my ($ids, $src, $dest) = @ARGV;
open my $idfh, "<", $ids or die $!;
my %want;
while (<$idfh>) { chomp; $want{$_} = 1 if $_ ne ""; }
close $idfh;
my $in;
if ($src =~ /\.gz$/) { open $in, "-|", "gzip", "-dc", $src or die $!; }
else { open $in, "<", $src or die $!; }
open my $out, ">", $dest or die $!;
my $on = 0;
while (<$in>) {
    if (/^>/) {
        my ($id) = /^>(\S+)/;
        $on = $want{$id} ? 1 : 0;
    }
    print $out $_ if $on;
}
close $in;
close $out;
PERL
}

digest "$OLD" > "$WORK/old.md5"
digest "$NEW" > "$WORK/new.md5"
awk 'NR==FNR { m[$1] = $2; next }
     { if (!($1 in m) || m[$1] != $2) print $1 }
' "$WORK/old.md5" "$WORK/new.md5" > "$WORK/changed.ids"
awk 'NR==FNR { m[$1] = $2; next }
     ($1 in m) && m[$1] == $2 { print $1 }
' "$WORK/old.md5" "$WORK/new.md5" > "$WORK/stable.ids"

got=$("$DIAMOND" dbinfo --db "$NEW" | awk '/Letters/ { print $NF; exit }')
if [ "$got" != "$PINNED_LETTERS" ]; then
    echo "STOP dbinfo letters $got != $PINNED_LETTERS" >&2
    exit 2
fi

: > "$WORK/disc.m8"
if [ -s "$WORK/changed.ids" ]; then
    extract "$WORK/changed.ids" "$NEW" "$WORK/changed.fa"
    "$DIAMOND" makedb --in "$WORK/changed.fa" --db "$WORK/changed" --threads "$CPU"
    "$DIAMOND" blastp --db "$WORK/changed" --query "$QUERIES" --out "$WORK/disc.m8" \
        --min-score 40 -k 0 --motif-masking 0 -b 2.0 --comp-based-stats 1 \
        --threads "$CPU" --dbsize "$got" \
        --outfmt 6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore
fi

awk 'NR==FNR { st[$1] = 1; next }
     NF > 1 && st[$2] { print $1 "\t" $2 }
' "$WORK/stable.ids" "$OLD_M8" > "$WORK/cand.pairs"
awk 'NF > 1 { print $1 "\t" $2 }' "$WORK/disc.m8" >> "$WORK/cand.pairs"
awk '/^>/ { print n "\t" substr($1, 2); n++ }' "$QUERIES" > "$WORK/q.order"
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

"$DIR/expert_update_hmmscan.sh" --plan < "$WORK/cand.tsv" > "$WORK/plan.txt"
awk '/^>/ { print substr($1, 2) }' "$QUERIES" > "$WORK/q.ids"

if [ ! -s "$WORK/plan.txt" ]; then
    : > "$OUT"
    exit 0
fi

rm -rf "$WORK/batches"
mkdir -p "$WORK/batches"
awk -v dir="$WORK/batches" -F '\t' '{ out = dir "/b" $1 ".ids"; print $2 > out }' "$WORK/plan.txt"
awk -v dir="$WORK/batches" -F '\t' '
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

batches=$(cut -f1 "$WORK/plan.txt" | sort -n -u)
for b in $batches; do
    awk -F '\t' -v b="$b" '$1 == b { print $2 }' "$WORK/batch.targets" > "$WORK/batches/b${b}.ids.subj"
    extract "$WORK/batches/b${b}.ids.subj" "$NEW" "$WORK/batches/b${b}.fa"
    "$DIAMOND" makedb --in "$WORK/batches/b${b}.fa" --db "$WORK/batches/b${b}" --threads "$CPU"
    "$DIAMOND" blastp --db "$WORK/batches/b${b}" --query "$WORK/batches/b${b}.faa" \
        --out "$WORK/batches/b${b}.m8" \
        --min-score 40 -k 0 --motif-masking 0 -b 2.0 --comp-based-stats 1 \
        --threads "$CPU" --dbsize "$got" \
        --outfmt 6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore
    rm -f "$WORK/batches/b${b}.dmnd" "$WORK/batches/b${b}.fa"
done

awk '
    NR == FNR { order[++n] = $1; known[$1] = 1; next }
    NF == 0 { next }
    {
        if (!($1 in known)) { bad++; next }
        body[$1] = body[$1] $0 "\n"
    }
    END {
        if (bad) exit 3
        for (i = 1; i <= n; i++) printf "%s", body[order[i]]
    }
' "$WORK/q.ids" "$WORK"/batches/b*.m8 > "$OUT"
rm -f "$WORK/changed.dmnd"
