# Batch planner matching acts.replay_batch.plan_batches.
# mode=keys  reads index<TAB>query<TAB>cand,cand and prints
#            freq<TAB>rarest<TAB>index<TAB>query<TAB>cands
# mode=chunks reads that stream already sorted and prints
#            batch<TAB>query with each batch in input order.
BEGIN { FS = "\t"; OFS = "\t" }

function chunk_cost(chunk,    total, start, hi, i, j, m, part, ucount, id) {
    total = 0
    for (start = 1; start <= n; start += chunk) {
        hi = start + chunk - 1
        if (hi > n) hi = n
        delete union
        for (i = start; i <= hi; i++) {
            m = split(cand_of[i], parts, ",")
            for (j = 1; j <= m; j++) if (parts[j] != "") union[parts[j]] = 1
        }
        ucount = 0
        for (id in union) ucount++
        part = hi - start + 1
        total += startup + press * ucount + part * ucount
    }
    return total
}

function better(cost, chunk, bcost, bchunk) {
    return (cost < bcost) || (cost == bcost && chunk < bchunk)
}

mode == "keys" {
    if ($3 == "") next
    n++
    idx[n] = $1
    qname[n] = $2
    m = split($3, ids, ",")
    delete seen
    built = ""
    for (i = 1; i <= m; i++) {
        if (ids[i] == "" || seen[ids[i]]) continue
        seen[ids[i]] = 1
        freq[ids[i]]++
        built = (built == "" ? ids[i] : built "," ids[i])
    }
    uniq[n] = built
    next
}

mode == "chunks" {
    n++
    index_of[n] = $3 + 0
    qname[n] = $4
    cand_of[n] = $5
    next
}

END {
    if (mode == "keys") {
        for (r = 1; r <= n; r++) {
            m = split(uniq[r], ids, ",")
            best = ids[1]
            for (i = 2; i <= m; i++) {
                id = ids[i]
                if (freq[id] < freq[best] || (freq[id] == freq[best] && id < best)) best = id
            }
            print freq[best], best, idx[r], qname[r], uniq[r]
        }
        exit
    }
    if (mode != "chunks" || n == 0) exit
    if (startup == "") startup = 2000
    if (press == "") press = 84
    startup += 0
    press += 0
    s = 1
    ns = 0
    while (s < n) {
        sizes[++ns] = s
        s *= 2
    }
    sizes[++ns] = n
    best = sizes[1]
    best_cost = chunk_cost(best)
    for (i = 2; i <= ns; i++) {
        cost = chunk_cost(sizes[i])
        if (better(cost, sizes[i], best_cost, best)) {
            best = sizes[i]
            best_cost = cost
        }
    }
    lo = int(best / 2)
    if (lo < 1) lo = 1
    hi = best * 2
    if (hi > n) hi = n
    step = int((hi - lo) / 20)
    if (step < 1) step = 1
    for (c = lo; c <= hi; c += step) {
        cost = chunk_cost(c)
        if (better(cost, c, best_cost, best)) {
            best = c
            best_cost = cost
        }
    }
    batch = 0
    for (start = 1; start <= n; start += best) {
        hi = start + best - 1
        if (hi > n) hi = n
        m = 0
        for (i = start; i <= hi; i++) pos[++m] = i
        for (i = 2; i <= m; i++) {
            j = i
            while (j > 1 && index_of[pos[j]] < index_of[pos[j - 1]]) {
                tmp = pos[j]
                pos[j] = pos[j - 1]
                pos[j - 1] = tmp
                j--
            }
        }
        for (i = 1; i <= m; i++) print batch, qname[pos[i]]
        batch++
    }
}
