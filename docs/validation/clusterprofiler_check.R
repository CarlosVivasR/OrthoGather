# Does another enrichment tool return the example's terms from the same data?
#
# The worked example's two lists are tested with clusterProfiler's enricher()
# (hypergeometric test, Benjamini-Hochberg, gene sets of 10 to 500) against the
# same background and the same M. smegmatis GOA file of 28 July 2026, NOT
# annotations left out. Ancestors are added with clusterProfiler's buildGOmap(),
# which takes them from GO.db rather than from the go-basic.obo OrthoGather uses,
# and no minimum depth is applied, so the tested families differ a little.
# Two corrections: once across the three ontologies, as OrthoGather does, and
# separately for each ontology, as clusterProfiler's enrichGO() does.
#
# Needs R with clusterProfiler, GO.db and jsonlite (Bioconductor). From the
# repository root:  Rscript docs/validation/clusterprofiler_check.R

suppressPackageStartupMessages({
  library(clusterProfiler); library(GO.db); library(jsonlite)
})
ex <- "example_analysis/input_dataset"
out_dir <- "docs/validation/results/clusterprofiler"
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
read_ids <- function(f) { x <- trimws(readLines(file.path(ex, f))); unique(x[nzchar(x)]) }
bg <- read_ids("background_3181.txt")
lists <- list(decreased_306 = read_ids("foreground_down-regulated_306.txt"),
              increased_185 = read_ids("foreground_up-regulated_185.txt"))
published <- list(decreased_306 = "down-regulated_306", increased_185 = "up-regulated_185")

goa <- read.delim(gzfile("docs/validation/data/goa_2026-07-28/25827.M_smegmatis.goa.gz"),
                  comment.char = "!", header = FALSE, quote = "", stringsAsFactors = FALSE)
goa <- goa[!grepl("NOT", goa$V4), ]
t2g <- unique(buildGOmap(unique(data.frame(GO = goa$V5, Gene = goa$V2)))[, c("GO", "Gene")])
info <- suppressMessages(AnnotationDbi::select(GO.db, unique(t2g$GO), c("ONTOLOGY", "TERM"), "GOID"))
t2g$ONT <- info$ONTOLOGY[match(t2g$GO, info$GOID)]
t2n <- unique(data.frame(GO = info$GOID, NAME = info$TERM))

test <- function(fg, t2g_part) {
  e <- enricher(fg, universe = bg, TERM2GENE = t2g_part[, c("GO", "Gene")], TERM2NAME = t2n,
                pAdjustMethod = "BH", pvalueCutoff = 1, qvalueCutoff = 1,
                minGSSize = 10, maxGSSize = 500)
  if (is.null(e)) return(data.frame())
  d <- as.data.frame(e)[, c("ID", "Description", "GeneRatio", "BgRatio", "pvalue", "p.adjust")]
  rownames(d) <- NULL
  d
}

summary <- list(clusterProfiler = as.character(packageVersion("clusterProfiler")),
                GO.db = as.character(packageVersion("GO.db")))
for (nm in names(lists)) {
  pooled <- test(lists[[nm]], t2g)
  per <- do.call(rbind, lapply(c("BP", "MF", "CC"), function(o) {
    d <- test(lists[[nm]], t2g[t2g$ONT == o, ]); if (nrow(d)) d$ONT <- o; d }))
  write.table(pooled[order(pooled$p.adjust), ], file.path(out_dir, paste0(nm, "_pooled.tsv")),
              sep = "\t", quote = FALSE, row.names = FALSE)
  write.table(per[order(per$p.adjust), ], file.path(out_dir, paste0(nm, "_per_ontology.tsv")),
              sep = "\t", quote = FALSE, row.names = FALSE)
  pub_file <- Sys.glob(file.path("example_analysis/4_go_enrichment", published[[nm]], "table", "*.json"))[1]
  pub <- fromJSON(pub_file)
  pub_sig <- pub$GO[pub$p_fdr_bh < 0.05]
  cp_sig <- pooled$ID[pooled$p.adjust < 0.05]
  summary[[nm]] <- list(
    orthogather_terms = length(pub_sig),
    pooled = list(tested = nrow(pooled), significant = length(cp_sig),
                  orthogather_terms_returned = sum(pub_sig %in% cp_sig),
                  only_clusterprofiler = pooled[pooled$ID %in% setdiff(cp_sig, pub_sig),
                                                c("ID", "Description", "p.adjust")]),
    per_ontology = list(significant = per[per$p.adjust < 0.05, c("ID", "Description", "ONT", "p.adjust")]))
  cat(nm, ": OrthoGather", length(pub_sig), "terms; clusterProfiler pooled", length(cp_sig),
      "(", sum(pub_sig %in% cp_sig), "of OrthoGather's ); per ontology", sum(per$p.adjust < 0.05), "\n")
}
write(toJSON(summary, auto_unbox = TRUE, pretty = TRUE, digits = 6), file.path(out_dir, "summary.json"))
