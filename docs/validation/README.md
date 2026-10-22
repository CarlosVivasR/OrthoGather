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
| [Random foregrounds](#random-foregrounds) | Does each setting find nothing when there is nothing to find? | 2–7% of random lists (expected about 5%) |
| [Hidden annotations](#a-species-without-annotation) | Does expansion recover the functions of a species without annotation? | 35 of 40 *E. coli* processes; 2% of random lists |
| [Every combination of settings](#every-combination-of-settings) | Does any combination break a rule? | 1,296 combinations, 0 failures |

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
from the universe each setting tests against, and counts the draws with any term at FDR < 0.05. A
random draw has no biology behind it, so a calibrated setting gives about 5% or fewer.

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
proteins detected in the experiment as the background, as in the worked example.

Results: [`results/null_calibration/`](results/null_calibration/).

## A species without annotation

`expansion_benchmark.py` leaves one species' GOA file out of the worked example's analysis. It then
expands the foreground and the background to full orthogroups, which OrthoGather counts per
orthogroup, so only the annotations of orthologues in the other five species are available.

- **_E. coli_ K-12 hidden.** The benchmark uses 40 biological processes with experimental evidence
  in *E. coli* (15–80 proteins each, overlapping little). The foreground is each process's proteins,
  pure or diluted with as many random *E. coli* proteins; the background is the 4,403 *E. coli*
  proteins of the run.
  - The process, or a close relative, was recovered for **35 of 40** in both cases (30 and 29 with
    the exact term). With *E. coli*'s own annotations, all 40 are recovered.
  - The five not recovered are responses specific to the species (to light, X-rays, copper and
    other organisms) and protein complex oligomerization; orthology does not carry them.
- **Random foregrounds** of 40 *E. coli* proteins, in the same set-up: 2/100 gave a significant term.
- **The worked example with *M. smegmatis* hidden.** The published term of the increased set
  (*protein metabolic process*) is recovered. It comes among 39 terms, most of them translation,
  ribosome, transcription antitermination and heat-response functions consistent with the response
  to rifampicin, but also flagellar motility and nuclear components, which do not apply to
  *M. smegmatis*. The 21 terms of the decreased set are not: per orthogroup, they are not significant
  even with *M. smegmatis*' annotations, because those proteins belong to large families.

Limits:
- *E. coli* is the best-annotated bacterium. Some of its orthologues' annotations were derived from
  it, so recovery is optimistic for a species without close annotated relatives.
- Annotations of other lineages are counted too: with *M. smegmatis* hidden, flagellar motility
  appears through *E. coli* orthologues.

Counting per protein after expansion is not offered: there every paralogue counts as a separate
observation, and in the same set-up random foregrounds gave a significant term every time.

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
