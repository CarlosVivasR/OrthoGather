"""
Tests for the OrthoXML parser.

Covers:
  - Basic parse: species + genes + flat orthogroups
  - Namespace variants (orthoXML.org/2011/, 2014/)
  - Nested <paralogGroup> inside <orthologGroup> (must flatten)
  - protId vs geneId vs transcriptId fallback
  - Missing <groups> section → ValueError
  - Malformed XML → ValueError
  - File not found → FileNotFoundError
  - Output schema matches OrthoFinder (Orthogroup + species + Total columns)
"""
from __future__ import annotations

import textwrap

import pandas as pd
import pytest

from orthogather.core.orthoxml import parse_orthoxml, write_orthofinder_tsvs


def _write(tmp_path, content):
    p = tmp_path / "test.orthoxml"
    p.write_text(textwrap.dedent(content).strip())
    return p


# ---------------------------------------------------------------------------
# Basic round-trip
# ---------------------------------------------------------------------------
class TestBasic:
    XML = """
    <?xml version="1.0" encoding="UTF-8"?>
    <orthoXML xmlns="http://orthoXML.org/2011/" version="0.5" origin="TestDB" originVersion="1.0">
      <species name="Homo sapiens" NCBITaxId="9606">
        <database name="UniProtKB" version="2025_03">
          <genes>
            <gene id="1" protId="P05067"/>
            <gene id="2" protId="P04637"/>
          </genes>
        </database>
      </species>
      <species name="Mus musculus" NCBITaxId="10090">
        <database name="UniProtKB" version="2025_03">
          <genes>
            <gene id="3" protId="P12023"/>
            <gene id="4" protId="P02340"/>
          </genes>
        </database>
      </species>
      <groups>
        <orthologGroup id="OG001">
          <geneRef id="1"/>
          <geneRef id="3"/>
        </orthologGroup>
        <orthologGroup id="OG002">
          <geneRef id="2"/>
          <geneRef id="4"/>
        </orthologGroup>
      </groups>
    </orthoXML>
    """

    def test_returns_three_objects(self, tmp_path):
        path = _write(tmp_path, self.XML)
        og_df, gc_df, meta = parse_orthoxml(path)
        assert isinstance(og_df, pd.DataFrame)
        assert isinstance(gc_df, pd.DataFrame)
        assert isinstance(meta, dict)

    def test_orthogroups_schema(self, tmp_path):
        og_df, _, _ = parse_orthoxml(_write(tmp_path, self.XML))
        assert list(og_df.columns) == ["Orthogroup", "Homo_sapiens", "Mus_musculus"]
        assert len(og_df) == 2
        # OrthoFinder-compatible "src|ACC|ACC" format
        assert og_df.iloc[0]["Homo_sapiens"] == "src|P05067|P05067"
        assert og_df.iloc[0]["Mus_musculus"] == "src|P12023|P12023"

    def test_gene_count_schema(self, tmp_path):
        _, gc_df, _ = parse_orthoxml(_write(tmp_path, self.XML))
        assert list(gc_df.columns) == ["Orthogroup", "Homo_sapiens", "Mus_musculus", "Total"]
        assert (gc_df["Total"] == gc_df[["Homo_sapiens", "Mus_musculus"]].sum(axis=1)).all()

    def test_metadata_captures_origin(self, tmp_path):
        _, _, meta = parse_orthoxml(_write(tmp_path, self.XML))
        assert meta["source_format"] == "orthoxml"
        assert meta["orthoxml_version"] == "0.5"
        assert meta["origin"] == "TestDB"
        assert meta["origin_version"] == "1.0"
        assert meta["n_species"] == 2
        assert meta["n_orthogroups"] == 2
        assert meta["n_genes"] == 4
        assert {"name": "UniProtKB", "version": "2025_03"} in meta["databases"]


# ---------------------------------------------------------------------------
# Nested paralogs (must be flattened into one OG row)
# ---------------------------------------------------------------------------
class TestNestedParalogs:
    XML = """
    <?xml version="1.0" encoding="UTF-8"?>
    <orthoXML xmlns="http://orthoXML.org/2014/" version="0.5" origin="OrthoDB">
      <species name="Homo sapiens" NCBITaxId="9606">
        <database name="UniProt" version="2024_06">
          <genes>
            <gene id="h1" protId="P01"/>
          </genes>
        </database>
      </species>
      <species name="Mus musculus" NCBITaxId="10090">
        <database name="UniProt" version="2024_06">
          <genes>
            <gene id="m1" protId="M01"/>
            <gene id="m2" protId="M02"/>
          </genes>
        </database>
      </species>
      <groups>
        <orthologGroup id="123">
          <geneRef id="h1"/>
          <paralogGroup>
            <geneRef id="m1"/>
            <geneRef id="m2"/>
          </paralogGroup>
        </orthologGroup>
      </groups>
    </orthoXML>
    """

    def test_paralogs_collapsed_into_one_og(self, tmp_path):
        og_df, _, _ = parse_orthoxml(_write(tmp_path, self.XML))
        # one row only
        assert len(og_df) == 1
        # mouse cell contains both paralogs comma-joined
        mouse = og_df.iloc[0]["Mus_musculus"]
        assert "M01" in mouse and "M02" in mouse
        assert mouse.count(",") == 1

    def test_id_prefix_normalised(self, tmp_path):
        og_df, _, _ = parse_orthoxml(_write(tmp_path, self.XML))
        # "123" -> "OG123"
        assert og_df.iloc[0]["Orthogroup"] == "OG123"

    def test_namespace_variant_2014(self, tmp_path):
        """The 2014 namespace must parse just like 2011."""
        _, _, meta = parse_orthoxml(_write(tmp_path, self.XML))
        assert meta["n_species"] == 2
        assert meta["origin"] == "OrthoDB"


# ---------------------------------------------------------------------------
# Accession fallbacks (protId / geneId / transcriptId)
# ---------------------------------------------------------------------------
class TestAccessionFallback:
    XML_GENEID_ONLY = """
    <?xml version="1.0" encoding="UTF-8"?>
    <orthoXML xmlns="http://orthoXML.org/2011/" version="0.5">
      <species name="X" NCBITaxId="1">
        <database name="N" version="v">
          <genes>
            <gene id="1" geneId="ENSG00000001"/>
          </genes>
        </database>
      </species>
      <groups>
        <orthologGroup id="OGA">
          <geneRef id="1"/>
        </orthologGroup>
      </groups>
    </orthoXML>
    """

    def test_falls_back_to_geneId(self, tmp_path):
        og_df, _, _ = parse_orthoxml(_write(tmp_path, self.XML_GENEID_ONLY))
        assert "ENSG00000001" in og_df.iloc[0]["X"]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------
class TestErrors:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_orthoxml("/tmp/__definitely_not_there.orthoxml")

    def test_malformed_xml(self, tmp_path):
        p = tmp_path / "bad.orthoxml"
        p.write_text("<not actually xml>")
        with pytest.raises(ValueError, match="(?i)not a valid xml"):
            parse_orthoxml(p)

    def test_wrong_root_element(self, tmp_path):
        p = tmp_path / "wrong.xml"
        p.write_text('<?xml version="1.0"?><something/>')
        with pytest.raises(ValueError, match="OrthoXML"):
            parse_orthoxml(p)

    def test_no_groups_section(self, tmp_path):
        xml = """
        <?xml version="1.0"?>
        <orthoXML xmlns="http://orthoXML.org/2011/" version="0.5">
          <species name="X" NCBITaxId="1">
            <database name="N" version="v"><genes><gene id="1" protId="P"/></genes></database>
          </species>
        </orthoXML>
        """
        with pytest.raises(ValueError, match="no <groups>"):
            parse_orthoxml(_write(tmp_path, xml))


# ---------------------------------------------------------------------------
# Disk output (write_orthofinder_tsvs)
# ---------------------------------------------------------------------------
class TestDiskOutput:
    def test_writes_three_files(self, tmp_path):
        og_df, gc_df, _ = parse_orthoxml(_write(tmp_path, TestBasic.XML))
        out = tmp_path / "out"
        write_orthofinder_tsvs(og_df, gc_df, out)
        for fname in ("Orthogroups.tsv", "Orthogroups.GeneCount.tsv",
                      "Orthogroups_SingleCopyOrthologues.txt"):
            assert (out / fname).exists(), f"{fname} not written"

    def test_singlecopy_file_lists_single_copy_ogs(self, tmp_path):
        """Both OGs in TestBasic.XML are 1:1, so the single-copy file should
        list both of them."""
        og_df, gc_df, _ = parse_orthoxml(_write(tmp_path, TestBasic.XML))
        out = tmp_path / "out"
        write_orthofinder_tsvs(og_df, gc_df, out)
        sc = (out / "Orthogroups_SingleCopyOrthologues.txt").read_text().split()
        assert "OG001" in sc and "OG002" in sc
