# Validation

These scripts check that OrthoGather does what the paper says, on data where the right answer is
known. They drive the application's real routes (the same code the browser calls), in a temporary
folder, so they never touch an installation's history or data. Every input is in the repository:
the worked example's OrthoFinder export (`example_analysis/1_orthofinder/`) and the EBI GOA files it
was analysed with, generated on 28 July 2026 (`data/goa_2026-07-28/`, CC BY 4.0, UniProt-GOA).

The results below were produced with OrthoGather 2.2.0 in the pinned environment of
`environment.yml`; the JSON files in `results/` hold every number.

| Validation | Question | Result |
|---|---|---|
| [Worked example](#worked-example) | Does the code reproduce the paper? | 35/35 numbers |
| [Random foregrounds](#random-foregrounds) | Is each setting right when proteins are independent, as the test assumes? | 2–7% of random lists (expected about 5%) |
| [Hidden annotations](#a-species-without-annotation) | Does expansion recover the functions of a species without annotation? | In an ideal case, 27 of 40 *E. coli* processes with the exact term; 2% of random lists |
| [Every combination of settings](#every-combination-of-settings) | Does any combination break a rule? | 1,296 combinations, 0 failures |
| [Independent implementation](#independent-implementation) | Do the statistics match code written without GOATOOLS? | Identical in every setting tested |
| [Sensitivity of the example](#sensitivity-of-the-example) | How do the example's results change with the settings? | Table S6 of Supplementary File S1 |

Run any of them from the repository root, in the `orthogather` environment:

```bash
python docs/validation/verify_example.py
```

## Worked example

`verify_example.py` rebuilds the worked example and checks every number that the paper and
Supplementary File S1 quote:
- the orthogroups and the proteins mapped;
- the UpSet intersections and the Table S3 counts;
- the GO annotation coverage;
- the 21 and 1 enriched terms, the 250 and 162 proteins tested and the 2,470 annotated background
  proteins;
- the sensitivity numbers of S1.

It also compares the regenerated figure data and enrichment results with the published files in
`example_analysis/`. Result: **35/35**, with the published files reproduced term by term to 12
decimal places of the q-value ([`results/verify_example.json`](results/verify_example.json)). GitHub
Actions runs this check on every change.

## Random foregrounds

`null_calibration.py` draws 100 random foregrounds of 306 proteins (the size of the decreased set)
from the universe each setting tests against, and counts the draws with any term at FDR < 0.05.
Random draws are what the test assumes: independent proteins with no biology behind them. So this
checks how each setting is implemented, and a correct one gives about 5% or fewer. It is not the
false-positive rate of real lists. In an experiment, the proteins of an operon or of a family change
together, and any over-representation test that treats proteins as independent then gives more
false positives than its nominal rate (Goeman and Bühlmann 2007,
[doi:10.1093/bioinformatics/btm051](https://doi.org/10.1093/bioinformatics/btm051)). Counting per
orthogroup allows for families, not for operons.

| Setting | Drawn from | Draws with a significant term (95% CI) |
|---|---|---|
| Per protein, pasted background (the paper's setting) | the 3,181 detected proteins | 2/100 (0.6–7.0%) |
| Per orthogroup, pasted background | the 3,181 detected proteins | 3/100 (1.0–8.5%) |
| Both sets expanded (counted per orthogroup) | the 3,181 detected proteins | 3/100 (1.0–8.5%) |
| "Use all GOA files", per protein | *M. smegmatis*' annotated proteome | 2/100 (0.6–7.0%) |
| "Use all GOA files", per orthogroup | *M. smegmatis*' proteome | 7/100 (3.4–13.8%) |
| *M. smegmatis* without GOA file, both sets expanded | the 3,181 detected proteins | 3/100 (1.0–8.5%) |
| *M. smegmatis* without GOA file, "Use all GOA files" | *M. smegmatis*' proteome | 5/100 (2.2–11.2%) |

Every interval includes 5%. With 100 draws per setting, 7/100 cannot be told apart from 5%.

A warning rather than a calibration: random sets of the 3,181 *detected* proteins tested against the
whole annotated proteome ("Use all GOA files") gave a significant term in 36 of 100 draws (27–46%), mostly phosphorus and nucleotide metabolism. Detected
proteins are not a random part of the proteome (abundant, housekeeping functions are over-
represented), so testing an experiment's hits against the whole proteome finds that bias. Paste the
proteins detected in the experiment as the background, as in the worked example. With the example's
own lists, the whole proteome as background gives 35 and 33 terms instead of 21 and 1
([Sensitivity of the example](#sensitivity-of-the-example)).

Results: [`results/null_calibration/`](results/null_calibration/).

## A species without annotation

`expansion_benchmark.py` leaves one species' GOA file out of the worked example's analysis. It then
expands the foreground and the background to full orthogroups, which OrthoGather counts per
orthogroup, so only the annotations of orthologues in the other five species are available.

- **_E. coli_ K-12 hidden.** The benchmark draws 40 biological processes with experimental evidence
  in *E. coli* (15–80 proteins each, overlapping little) from 278 candidates, sorted and shuffled with
  a fixed seed so that every run draws the same 40. The foreground is each process's proteins, pure
  or diluted with as many random *E. coli* proteins; the background is the 4,403 *E. coli* proteins
  of the run.
  - The exact term was recovered for **27 of 40** in both cases; counting a close relative too (a
    descendant, or an ancestor at most two levels up), for 37 (pure) and 35 (diluted). With
    *E. coli*'s own annotations, all 40 are recovered with the exact term.
  - Not recovered: responses to UV and to ionizing radiation and protein homooligomerization, and,
    when diluted, also cellular response to reactive oxygen species and regulation of catabolic
    process.
  - This is an ideal case: each foreground is a whole process, which no real list is.
- **Random foregrounds** of 40 *E. coli* proteins, in the same set-up: 2/100 gave a significant term.
- **The worked example with *M. smegmatis* hidden.** The published term of the increased set
  (*protein metabolic process*) is recovered. It comes among 39 terms, most of them translation,
  ribosome, transcription antitermination and heat-response functions consistent with the response
  to rifampicin, but also seven that cannot apply to a mycobacterium: flagellar motility, the
  nucleus and membrane-bounded organelles. They come from annotations of *E. coli* RNA polymerase
  subunits (to motility, and to a transcription complex that GO places in the nucleus) and of
  *P. aeruginosa* motility mutants, and they appear too when *M. smegmatis*' own annotations are
  used ([Sensitivity of the example](#sensitivity-of-the-example)). The 21 terms of the decreased set
  are not recovered: per orthogroup, they are not significant even with *M. smegmatis*' annotations.

Limits:
- *E. coli* is the best-annotated bacterium. Some of its orthologues' annotations were derived from
  it, so recovery is optimistic for a species without close annotated relatives.
- Annotations of other lineages are counted too: flagellar motility and the nucleus appear through
  *E. coli* and *P. aeruginosa* annotations, with or without *M. smegmatis*' own.
- Recovery rests on the donors' electronic annotations, which are 87% of their biological-process
  annotations. A re-run of the *E. coli* benchmark with donor annotations removed by kind (exact
  term, pure foregrounds):

  | Donor annotations | Exact term |
  |---|---|
  | All | 27/40 |
  | Without those citing an *E. coli* protein in with/from | 27/40 |
  | Also without IBA and TreeGrafter (GO_REF:0000118) | 24/40 |
  | Experimental only | 1/40 |

  Annotations derived from *E. coli* itself do not explain the result. A species whose relatives
  have experimental annotations only would get almost nothing back.
- Counted per orthogroup, the permutation p-values depend on the order in which the background is
  pasted, as on the seed: terms near the threshold can enter or leave with another order. The
  Provenance sheet of each results file records a SHA-256 of the background in its order, so a
  run can be repeated exactly.
- Isolates that are not in UniProt need their own OrthoFinder run, uploaded to OrthoGather; their
  proteins are then tested through the annotations of their orthologues.

Counting per protein after expansion is not offered: there every paralogue would count as a
separate observation.

Results: [`results/expansion_benchmark/`](results/expansion_benchmark/).

## Every combination of settings

`combinations_matrix.py` runs `tests/test_go_combinations.py` in full on a synthetic analysis with
the hard cases:
- three species: one with a complete GOA file, one annotated at about 40% and one without a GOA file;
- paralogue families of unequal size;
- single-species orthogroups;
- proteins in no orthogroup;
- IEA, curated and experimental evidence.

The combinations come from multiplying:

| Setting | Options |
|---|---|
| Foreground list | 6: a signal, a paralogue family, a random list, mixed formats, one identifier, identifiers of another species and unknown ones |
| Background | 3: pasted, pasted and expanded, "Use all GOA files" |
| Foreground expansion | on / off |
| Single-copy filter | on / off |
| Counting mode | 2 |
| Evidence setting | 3 |

That makes 1,296 combinations. Each analysis is checked against these rules:
- the counting mode applied, and the notes that explain it;
- the accounting of every pasted identifier;
- possible counts;
- Fisher p-values equal to SciPy's;
- a Benjamini–Hochberg correction that reproduces;
- the results file and the response agreeing.

Between analyses it also checks that:
- an expanded set gives the same result whichever counting mode is asked for;
- "Use all GOA files" per orthogroup equals the species' proteome pasted and expanded;
- the single-copy filter changes nothing without expansion;
- a new session gives the same results.

Result: **0 failures**.
- 922 combinations gave results.
- The others had nothing to test, for example a species without a GOA file and no expansion, or an
  evidence filter that leaves no annotation. The application answers those with a message that says
  what to do. A single-copy expansion of a paralogue family is refused.

The reduced version (144 analyses, about a minute) runs with the test suite on every change.

Results: [`results/combinations_matrix/`](results/combinations_matrix/).

## Independent implementation

`independent_check.py` recomputes the enrichment without GOATOOLS or the application's code: ontology
parsing, propagation over `is_a` and `part_of`, term depth, the universe, the one-sided Fisher test,
the term-size and depth filters and the Benjamini–Hochberg correction. For the two foregrounds of the
worked example, the three evidence settings and the two universe conventions, and for "Use all GOA
files", the counts, p-values, q-values and the size of the correction family are identical to
OrthoGather's. Per orthogroup, the hypergeometric statistic is identical, and the permutation
p-values of the ten smallest terms agree with a brute-force permutation that uses another random
generator (largest |z| 2.0 over the 20 terms, with the application's 21,760 shuffles and 10,000
brute-force ones).

Results: [`results/independent_check.json`](results/independent_check.json).

## Sensitivity of the example

`sensitivity_example.py` analyses the paper's lists with the published settings and with one setting
changed at a time. This is Table S6 of Supplementary File S1.
- The 21 terms of the decreased set remain with a two-sided test and become 15 at minimum depth 5,
  1 with one universe per ontology, and none with non-electronic evidence or counted per orthogroup.
  Counted per orthogroup, the increased set gives 5 terms, translation among them.
- With the whole annotated proteome as background ("Use all GOA files"), the decreased and increased
  sets give 35 and 33 terms instead of 21 and 1.
- With both sets expanded to orthogroups, the decreased set gives none and the increased set 60, or
  39 with the *M. smegmatis* GOA file left out. Seven of them cannot apply to a mycobacterium (three
  of flagellar motility, the nucleus, a nuclear complex and two of membrane-bounded organelles; the
  script lists the terms under these GO branches).

The per-orthogroup rows use permutation p-values, and terms close to the threshold change with the
seed. `python docs/validation/sensitivity_example.py seeds` repeats them with seeds 1–50:

| Row | Decreased (306) | Increased (185) | All 491 |
|---|---|---|---|
| Counted per orthogroup | 0 | 3–5 | 1–6 |
| Both sets expanded | 0–4 | 51–63 | 5–11 |
| Both sets expanded, *M. smegmatis* GOA file left out | 0 | 33–39 | 0–2 |

The application's seed gives 0, 5 and 4; 0, 60 and 9; and 0, 39 and 2. The seven terms that cannot
apply to a mycobacterium come out with every seed.

Results: [`results/sensitivity_example.json`](results/sensitivity_example.json) and
[`results/sensitivity_seeds/`](results/sensitivity_seeds/).
