# Email draft — scope lock with Zhang

**To:** Jiapeng Zhang (course instructor)  
**Subject:** CSCI 270 research project scope — STAR RNA-seq aligner speedup

---

Hi Professor Zhang,

Thank you for clarifying the research project expectations.

I will work on improving [STAR](https://github.com/alexdobin/STAR) (Dobin et al.), the widely used RNA-seq aligner. My goal is not to replace STAR globally, but to deliver a **scoped, reproducible ≥2× wall-clock speedup** on a fixed benchmark workload while keeping mapping quality essentially unchanged (same or statistically equivalent mapping rate / accuracy metrics on that benchmark).

Deliverables for the course:
1. Code (optimization / reimplementation of a profiled hot path)
2. Benchmark scripts and raw timing tables vs stock STAR
3. A short write-up describing method, experiments, and results

Does this scope work for the A-level research project requirement?

Best,  
Josh Terranova

---

After he replies **yes**, copy the agreed workload/hardware/metrics into `SCOPE.md`.

---

## Reply received 2026-09-08 (locked)

Zhang confirmed A if:

1. Output same as STAR  
2. Fair comparison (same machine, same threads; e.g. 1 thread)  
3. Test on **10** Illumina short-read datasets  
4. ≥2× based on **wall-clock** end-to-end  

→ Recorded in `star/docs/SCOPE.md`.
