import os
import zipfile
import shutil
import re
import time
import socket
import threading
import webbrowser
import gzip
import json
import requests
import subprocess
import threading
import webbrowser
import traceback
import datetime
from pathlib import Path
from textwrap import wrap
from itertools import cycle
from typing import List, Optional, Dict, Set
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.gridspec import GridSpec
from matplotlib.ticker import MaxNLocator
import matplotlib.cm as cm
from upsetplot import UpSet, from_memberships
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_file, session, jsonify, send_from_directory, Response, stream_with_context
)
from flask_session import Session
from goatools.obo_parser import GODag
from goatools.anno.gaf_reader import GafReader
from goatools.goea.go_enrichment_ns import GOEnrichmentStudy, GOEnrichmentStudyNS
from collections import defaultdict

import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logging.getLogger('werkzeug').setLevel(logging.WARNING)

def respond(ok: bool, msg: str, *, where=None, hint=None, payload=None, code=200):
    """
    Uniform JSON response for GO.
    ok=True/False, msg=human-readable message, where=workflow step,
    hint=solution suggestion, payload=dict with extra data.
    """
    data = {"success": ok, "message": msg}
    if where:   data["where"] = where
    if hint:    data["hint"] = hint
    if payload: data.update(payload)

    if ok:
        logging.info(f"{where or 'GO'}: {msg}")
    else:
        logging.error(f"{where or 'GO'}: {msg} | hint={hint}")

    return jsonify(data), code

# ------------------------
# App
# ------------------------
app = Flask(__name__)
app.secret_key = 'your_secret_key'  

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join("static", "flask_sessions")
app.config["SESSION_PERMANENT"] = False
Session(app)

# ------------------------
# Working directories
# ------------------------
STATIC_FOLDER = "static"
PROTEOMES_FOLDER = "Proteomas"
GOA_DOWNLOAD_FOLDER = "GOAfiles"
RESULTS_FOLDER = os.path.join(STATIC_FOLDER, "results")
JSON_PATH = "static/Proteomes_json/proteomes_list.json"
GO_ROOT_OBO = "go-basic.obo"  # located in the root directory, next to app.py

# Create required folders
os.makedirs(PROTEOMES_FOLDER, exist_ok=True)
os.makedirs(GOA_DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)
os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)

# ------------------------
# Global variables
# ------------------------
orthogroups_df = None
gene_count_df = None
species_selected = None
ortogrupos_por_combinacion = None
abreviaturas = None
selected_orthogroups = None
species_urls = None 
selected_orthogroups_list = None
final_protein_list = None


def find_free_port(start=5000, end=5100):
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free ports in range {start}-{end}")

def open_browser(port):
    webbrowser.open(f"http://127.0.0.1:{port}")

def cargar_datos_carpeta(ruta_carpeta):
    print(f"Files in folder '{ruta_carpeta}':")
    try:
        print(os.listdir(ruta_carpeta))
    except Exception as e:
        print(f"[WARN] Could not list '{ruta_carpeta}': {e}")

    gene_count_path = os.path.join(ruta_carpeta, 'Orthogroups.GeneCount.tsv')
    orthogroups_path = os.path.join(ruta_carpeta, 'Orthogroups.tsv')
    single_copy_path = os.path.join(ruta_carpeta, 'Orthogroups_SingleCopyOrthologues.txt')
    unassigned_path  = os.path.join(ruta_carpeta, 'Orthogroups_UnassignedGenes.tsv')

    # 👉 Only these two are mandatory
    if not os.path.exists(gene_count_path):
        raise FileNotFoundError(f"File not found: {gene_count_path}")
    if not os.path.exists(orthogroups_path):
        raise FileNotFoundError(f"File not found: {orthogroups_path}")

    # Mandatory loads
    gene_count_df  = pd.read_csv(gene_count_path, sep='\t')
    orthogroups_df = pd.read_csv(orthogroups_path, sep='\t')

    # Optional loads
    single_copy_df = None
    if os.path.exists(single_copy_path):
        try:
            single_copy_df = pd.read_csv(single_copy_path, sep='\t')
        except Exception as e:
            print(f"[WARN] Could not read SingleCopy (continuing): {e}")
    else:
        print(f"[WARN] Optional file not found (continuing): {single_copy_path}")

    unassigned_df = None
    if os.path.exists(unassigned_path):
        try:
            unassigned_df = pd.read_csv(unassigned_path, sep='\t')
        except Exception as e:
            print(f"[WARN] Could not read Unassigned (continuing): {e}")
    else:
        print(f"[WARN] Optional file not found (continuing): {unassigned_path}")

    return gene_count_df, orthogroups_df, single_copy_df, unassigned_df

def eliminar_archivo(ruta_archivo):
    if os.path.exists(ruta_archivo):
        os.remove(ruta_archivo)

def crear_directorio_plots():
    if not os.path.exists(os.path.join('static', 'plots')):
        os.makedirs(os.path.join('static', 'plots'))

def generar_figura_1(gene_count_df):
    try:
        fig, ax = plt.subplots(figsize=(10, 6))

        # Data cleaning
        data = gene_count_df['Total'].replace([np.inf, -np.inf], np.nan).dropna()

        # Safe calculation of the last bin
        penultimo_bin = 1000.5
        max_val_usuario = int(data.max()) + 1
        if max_val_usuario <= penultimo_bin:
            ultimo_bin = penultimo_bin + 100  # ensure increasing order
        else:
            ultimo_bin = max_val_usuario

        # Defined bins
        bins = [
            0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5,
            12.5, 15.5, 18.5, 20.5, 25.5, 30.5, 35.5, 40.5,
            50.5, 60.5, 70.5, 80.5, 90.5, 100.5,
            200.5, 300.5, 400.5, 500.5, penultimo_bin, ultimo_bin
        ]

        bins = sorted(set(bins))  # removes duplicates if `ultimo_bin == penultimo_bin`

        labels = [
            '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
            '11-12', '13-15', '16-18', '19-20', '21-25',
            '26-30', '31-35', '36-40', '41-50',
            '51-60', '61-70', '71-80', '81-90', '91-100',
            '101-200', '201-300', '301-400', '401-500', '501-1000', '1001+'
        ]

        # Length validation
        if len(labels) != len(bins) - 1:
            print(f"[WARNING] Figure 1 will not be generated: number of labels ({len(labels)}) "
                  f"does not match bins-1 ({len(bins)-1})")
            return None

        grouped_data = pd.cut(data, bins=bins, labels=labels, include_lowest=True, right=False)
        counts = grouped_data.value_counts().sort_index()

        sns.barplot(x=counts.index, y=counts.values, ax=ax, color='orange')

        # Separator lines
        separator_positions = {
            '10_11-12': 9.5,
            '19-20_21-25': 13.5,
            '36-40_41-50': 17.5,
            '91-100_101-200': 23.5,
            '401-500_501-1000': 27.5
        }
        for position in separator_positions.values():
            ax.axvline(x=position, color='black', linestyle='--')

        # Explanatory text
        text_positions = {
            (5, 5): 'INC by 1 ',
            (10, 13): 'INC by 2 ',
            (15.5, 15.5): 'INC by 5 ',
            (20.5, 20.5): 'INC by 10 ',
            (25.5, 25.5): 'INC by 100 ',
            (28.5, 28.5): 'INC by 500 ',
        }
        fixed_height = counts.max() * 0.7
        for (start, end), text in text_positions.items():
            midpoint = (start + end) / 2
            ax.text(midpoint, fixed_height, text, ha='center', fontsize=14, color='grey', rotation='vertical')

        ax.set_title('Protein Distribution by Orthogroup', fontsize=23)
        ax.set_xlabel('Number of Proteins', fontsize=20)
        ax.set_ylabel('Frequency', fontsize=20)
        ax.tick_params(axis='x', rotation=90)
        ax.set_ylim(0, counts.max() + 220)

        for p in ax.patches:
            height = p.get_height()
            if height > 0:
                ax.text(p.get_x() + p.get_width() / 2, height + 0.8, f'{int(height)}',
                        ha='center', va='bottom', fontsize=12)

        plt.tight_layout()
        crear_directorio_plots()
        image_path = os.path.join('static', 'plots', 'figura_1.png')
        plt.savefig(image_path)
        plt.close(fig)

        return 'figura_1.png'

    except Exception as e:
        print(f"[ERROR] Could not generate figura_1: {e}")
        return None

def generar_figura_2(gene_count_df, axes=None):
    # Create axes if not provided
    if axes is None:
        fig, axes = plt.subplots(figsize=(10, 6))

    # Convert all numeric columns except the first one (orthogroup ID)
    gene_count_df.iloc[:, 1:] = gene_count_df.iloc[:, 1:].apply(pd.to_numeric, errors='coerce')

    # Select species (all columns except the first and last)
    species = gene_count_df.columns[1:-1]
    
    # Count how many species share orthogroups
    shared_orthogroups = gene_count_df[species].apply(lambda x: x > 0).sum(axis=1)
    unique_orthogroups = shared_orthogroups.value_counts().sort_index()

    # Ensure X values are strings for correct labeling
    x_labels = unique_orthogroups.index.astype(str)
    y_values = unique_orthogroups.values

    # Plot with explicit labels
    sns.barplot(x=x_labels, y=y_values, ax=axes)

    axes.set_title('Number of Unique and Shared Orthogroups', fontsize=16)
    axes.set_xlabel('Number of Species Sharing Orthogroups', fontsize=14)
    axes.set_ylabel('Count', fontsize=14)
    axes.tick_params(axis='x', rotation=0)

    # Save the image
    crear_directorio_plots()
    image_path = os.path.join('static', 'plots', 'figura_2.png')
    plt.savefig(image_path)
    plt.close(fig)

    return 'figura_2.png'

def generar_figura_3(gene_count_df, species, umbral=7):
    fig = plt.figure(figsize=(30, 17))  # Adjust figure size
    gs = GridSpec(2, 2, width_ratios=[2, 1], height_ratios=[3, 1])  # Relative size of subplots
    
    # Axes
    ax1 = fig.add_subplot(gs[0, 0])  # Axis for main plot
    ax2 = fig.add_subplot(gs[0, 1])  # Axis for abbreviation legend in table format
    ax3 = fig.add_subplot(gs[1, :])  # Axis for combination legend in table format
    ax2.axis('off')
    ax3.axis('off')

    abreviaturas = {}
    abreviatura_usadas = set()

    for sp in species:
        abbr = ''.join([p[0].upper() for p in sp.split()[:2]])
        
        # If the abbreviation has already been used, add a counter to make it unique
        contador = 1
        abbr_unica = abbr
        while abbr_unica in abreviatura_usadas:
            abbr_unica = f"{abbr}{contador}"
            contador += 1
        
        abreviaturas[sp] = abbr_unica
        abreviatura_usadas.add(abbr_unica)

    gene_count_df = gene_count_df[(gene_count_df[species] > 0).any(axis=1)]
    gene_counts = {sp: 0 for sp in species}
    combinaciones_generadas = {}

    for _, row in gene_count_df.iterrows():
        presentes = row[species][row[species] > 0].index.tolist()
        if len(presentes) == 1:
            gene_counts[presentes[0]] += row[presentes[0]]
        elif len(presentes) > 1:
            combinacion = ' + '.join(sorted(presentes))
            if combinacion in combinaciones_generadas:
                combinaciones_generadas[combinacion] += row[presentes].sum()
            else:
                combinaciones_generadas[combinacion] = row[presentes].sum()

    gene_counts.update(combinaciones_generadas)
    total_genes = sum(gene_counts.values())
    porcentajes = {k: (v / total_genes) * 100 for k, v in gene_counts.items() if (v / total_genes) * 100 > 0.5}
    etiquetas_abreviadas = {}
    combinaciones_numeradas = {}
    contador_combinacion = 1

    for combinacion, porcentaje in porcentajes.items():
        especies = combinacion.split(' + ')
        if len(especies) > umbral:
            etiqueta_numerada = f'Combination {contador_combinacion}'
            combinaciones_numeradas[etiqueta_numerada] = ' + '.join([abreviaturas[sp] for sp in especies])
            etiquetas_abreviadas[combinacion] = etiqueta_numerada
            contador_combinacion += 1
        else:
            etiquetas_abreviadas[combinacion] = ' + '.join([abreviaturas[sp] for sp in especies])

    n_especies = {k: len(k.split(' + ')) for k in porcentajes.keys()}
    utilizados = sorted(set(n_especies.values()))

    ### Color assignment using Viridis for species combinations
    cmap_combinaciones = cm.get_cmap('viridis')

    # Generate colors based on the number of "utilizados"
    colores_combinaciones = [cmap_combinaciones(i / (len(utilizados) - 1)) for i in range(len(utilizados))]

    # Assign colors to each species combination
    colores = {}
    for i, n in enumerate(utilizados):
        color = colores_combinaciones[i]  # Assign Viridis color
        for k in n_especies:
            if n_especies[k] == n:
                colores[k] = color  # Assign Viridis color to each species combination

    ### Light color palette for the abbreviation table
    colores_claros = ["#add8e6", "#90ee90", "#ffb6c1", "#ffa07a", "#f0e68c", "#e0ffff", "#fafad2", "#d3d3d3", "#ffefd5", "#ffdab9",
                    "#e6e6fa", "#dda0dd", "#b0e0e6", "#bc8f8f", "#f5f5dc", "#ffe4e1", "#d8bfd8", "#d2b48c", "#add8e6", "#deb887"]
    color_cycle_claros = cycle(colores_claros)

    abreviaturas_cortas = {sp: sp[:5] for sp in species}  # Short abbreviations (5 characters)
    unique_groups = list(set(abreviaturas_cortas.values()))  # Unique groups based on abbreviations
    group_colors = {group: next(color_cycle_claros) for group in unique_groups}  # Assign a light color to each group

    # Create abbreviation table
    tabla_abreviaturas = pd.DataFrame(list(abreviaturas.items()), columns=['Strain Name', 'Abbreviation'])
    tabla = ax2.table(cellText=tabla_abreviaturas.values, cellLoc='center', loc='center')

    # Get table position and size to adjust title dynamically
    renderer = fig.canvas.get_renderer()
    tabla_pos = tabla.get_window_extent(renderer)

    # Calculate new title position based on table height
    # We want it to be right above the table
    y_title_position = tabla_pos.ymax / fig.bbox.ymax + 0.06  # Adjust so "Abbreviations" appears right beside the table.

    # Place the title directly above the table (centered and Y-adjusted)
    ax2.annotate('Abbreviations', xy=(0.8, y_title_position), xycoords='figure fraction', 
                ha='center', fontsize=16, fontweight='bold', annotation_clip=False)

    # Apply colors and adjust table cell size
    for (i, j), cell in tabla.get_celld().items():
        strain_name = tabla_abreviaturas.iloc[i, 0] if i < len(tabla_abreviaturas) else ""
        group_key = strain_name[:5]
        if j == 0:
            cell.set_fontsize(9)
        elif j == 1:
            cell.set_fontsize(14)
        if group_key in group_colors:
            cell.set_facecolor(group_colors[group_key])

    # Scale table to make font size and spacing appropriate
    tabla.scale(1.2, 1.2)

    # Remove redundant title line
    # ax2.set_title('Abbreviations', fontsize=14, pad=10)  # Removed
    ax2.axis('off')

    # Main plot (ax1)
    bars = ax1.barh([etiquetas_abreviadas[k] for k in porcentajes.keys()], list(porcentajes.values()), color=[colores[k] for k in porcentajes.keys()])
    ax1.set_xlabel('Percentage of Proteins (%)', fontweight='bold',)
    ax1.set_title('Percentage of Unique and Shared Proteins between Species', fontweight='bold',)

    for bar in bars:
        width = bar.get_width()
        ax1.text(width + 0.1, bar.get_y() + bar.get_height()/2, f'{width:.2f}%', va='center', rotation=10)

    # Customize axes: hide top and right borders but keep X and Y axes
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)

    # Remove duplicates in legend and assign colors correctly
    unique_legend_labels = []
    species_legend_patches = []
    legend_colors = {}
    for k, n in n_especies.items():
        if n not in unique_legend_labels:
            legend_colors[n] = colores[k]
            unique_legend_labels.append(n)

    # Sort legend from fewer to more species
    sorted_legend_labels = sorted(unique_legend_labels)

    # Create sorted legend patches
    species_legend_patches = [plt.Line2D([0], [0], marker='o', color='w', label=f'{n} species', markersize=10, markerfacecolor=legend_colors[n]) for n in sorted_legend_labels]
    ax1.legend(handles=species_legend_patches, title="Number of Species", loc='upper right')


    # Combination table (Figure 3) - Only if combinations exist
    if combinaciones_numeradas:
        tabla_combinaciones = pd.DataFrame(list(combinaciones_numeradas.items()), columns=['Combination', 'Species'])
        tabla3 = ax3.table(cellText=tabla_combinaciones.values, cellLoc='center', loc='center')

        # Get table position and size to adjust title dynamically
        renderer = fig.canvas.get_renderer()
        tabla_pos = tabla3.get_window_extent(renderer)

        # Calculate new title position based on table height
        # We want it to be right above the table
        y_title_position = tabla_pos.ymax / fig.bbox.ymax - 0.005   # Adjust 0.02 if needed to fine-tune position

        # Place title directly above the table (centered and Y-adjusted)
        ax3.annotate('Combinations', xy=(0.55, y_title_position), xycoords='figure fraction', 
                    ha='center', fontsize=16, fontweight='bold', annotation_clip=False)

        # Apply colors from Figure 1 (colores) to corresponding rows in the table
        for (i, j), cell in tabla3.get_celld().items():
            if i < len(tabla_combinaciones):  # Apply only to valid rows
                # Get number of species in combination (second column)
                species_combination = tabla_combinaciones.iloc[i, 1]
                num_species = len(species_combination.split(' + '))
                # Apply corresponding color based on number of species
                for k in colores:
                    if n_especies[k] == num_species:
                        cell.set_facecolor(colores[k])  # Assign corresponding color
                # Adjust column widths
                if j == 0:  # First column (Combination)
                    cell.set_width(0.10)
                elif j == 1:  # Second column (Species)
                    cell.set_width(0.85)

        # Scale the table
        tabla3.scale(1.2, 1.2)

        ax3.axis('off')

    plt.tight_layout()

    crear_directorio_plots()
    
    image_path = os.path.join('static', 'plots', 'figura_3.png')
    plt.savefig(image_path)
    plt.close(fig)

    return 'figura_3.png', abreviaturas

def wrap_label(label, max_line_length=40, max_lines=2):
    label = label.replace("_", " ")
    if len(label) <= max_line_length:
        return label
    wrapped = wrap(label, max_line_length, break_long_words=True, break_on_hyphens=True)
    if len(wrapped) > max_lines:
        wrapped = wrapped[:max_lines]
        wrapped[-1] += "..."
    return '\n'.join(wrapped)

def calcular_element_size(n_species):
    return max(25, 60 - n_species * 2)

def calcular_figsize(n_species):
    width = 12
    height = min(9, 3.5 + n_species * 0.25)
    return (width, height)

def crear_upset_plot_ortogrupos(gene_count_df, species, title):
    memberships = []
    ortogrupos_por_combinacion = {}

    for _, row in gene_count_df[species].iterrows():
        combinacion = tuple([sp for sp, val in zip(species, row) if val > 0])
        memberships.append(combinacion)
        ortogrupos_por_combinacion.setdefault(combinacion, []).append(row.name)

    upset_data = from_memberships(memberships)
    n_species = len(species)
    fig = plt.figure(figsize=calcular_figsize(n_species))
    upset = UpSet(
        upset_data,
        subset_size='count',
        show_counts='%d',
        sort_by='degree',
        element_size=calcular_element_size(n_species)
    )
    upset.plot(fig=fig)

    ax = fig.axes[1]
    ylabels = [wrap_label(label.get_text()) for label in ax.get_yticklabels()]
    ax.set_yticklabels(ylabels)

    plt.suptitle(title, fontsize=16)
    crear_directorio_plots()
    image_path = os.path.join("static", "plots", f"{title.replace(' ', '_')}.png")
    plt.savefig(image_path, bbox_inches="tight", dpi=80)
    plt.close()

    return f"{title.replace(' ', '_')}.png", ortogrupos_por_combinacion

def crear_upset_plot_proteinas(gene_count_df, species, title, ortogrupos_por_combinacion):
    memberships = []
    protein_counts = {}

    for combinacion, ortogrupos in ortogrupos_por_combinacion.items():
        total_proteins = sum(gene_count_df.loc[ortogrupo, species].sum() for ortogrupo in ortogrupos)
        memberships.append(combinacion)
        protein_counts[combinacion] = total_proteins

    upset_data = from_memberships(memberships, data=list(protein_counts.values()))
    n_species = len(species)
    fig = plt.figure(figsize=calcular_figsize(n_species))
    upset = UpSet(
        upset_data,
        subset_size='sum',
        show_counts='%d',
        sort_by='degree',
        element_size=calcular_element_size(n_species)
    )
    upset.plot(fig=fig)

    ax = fig.axes[1]
    ylabels = [wrap_label(label.get_text()) for label in ax.get_yticklabels()]
    ax.set_yticklabels(ylabels)

    plt.suptitle(title, fontsize=16)
    crear_directorio_plots()
    image_path = os.path.join("static", "plots", f"{title.replace(' ', '_')}.png")
    plt.savefig(image_path, bbox_inches="tight", dpi=100)
    plt.close()

    return f"{title.replace(' ', '_')}.png", protein_counts

def _safe_sheet_label(label: str) -> str:
    # Excel forbids: : \ / ? * [ ]
    return re.sub(r"[:\\/?*\[\]]", "_", label)

def generar_archivo_excel_upsetplots_v2(
    ortogrupos_por_combinacion,
    orthogroups_df,
    species,
    abreviaturas,
    filename='UpSetPlot_Data_v2.xlsx'
):
    """
    Generates an Excel file with one sheet per species combination.
    Sheets are numbered (01-, 02-, ...) to avoid truncation collisions.
    Ordering mimics UpSet sort_by='degree':
      - degree (number of species) ascending
      - number of orthogroups descending
      - label ascending (stability)
    """

    combos = []
    for combinacion, ortogrupos in ortogrupos_por_combinacion.items():
        label = (
            ' + '.join([abreviaturas.get(sp, sp) for sp in combinacion])
            if abreviaturas else ' + '.join(list(combinacion))
        )
        label = label or "Unnamed_Combination"
        degree = len(combinacion)
        n_og = len(ortogrupos)
        combos.append((combinacion, ortogrupos, label, degree, n_og))

    combos.sort(key=lambda x: (x[3], -x[4], x[2]))

    with pd.ExcelWriter(filename) as writer:
        meta_rows = []

        for i, (combinacion, ortogrupos, label, degree, n_og) in enumerate(combos, start=1):
            combinacion_data = []

            for ortogrupo in ortogrupos:
                row_data = {'Orthogroup ID': ortogrupo}
                for sp in species:
                    if sp in orthogroups_df.columns:
                        proteins = orthogroups_df.at[ortogrupo, sp]
                        row_data[sp] = proteins if pd.notna(proteins) else ""
                combinacion_data.append(row_data)

            df_combinacion = pd.DataFrame(combinacion_data)

            prefix = f"{i:02d}-"
            clean_label = _safe_sheet_label(label)
            sheet_name = (prefix + clean_label)[:31]

            df_combinacion.to_excel(writer, sheet_name=sheet_name, index=False)

            meta_rows.append({
                "index": i,
                "sheet_name": sheet_name,
                "degree": degree,
                "n_orthogroups": n_og,
                "label": label,
                "species_combination": " | ".join(combinacion)
            })

        pd.DataFrame(meta_rows).to_excel(writer, sheet_name="Meta", index=False)

    return filename

def filter_orthogroups(orthogroups_df, uniprot_ids):
    """Filter orthogroups that contain genes with the provided UniProt IDs."""
    selected_orthogroups = []
    for idx, row in orthogroups_df.iterrows():
        genes = set()
        for col in orthogroups_df.columns[1:]:
            if pd.notna(row[col]):
                extracted_ids = [gene.split('|')[1] for gene in row[col].split(', ') if '|' in gene]
                genes.update(extracted_ids)
        if genes & set(uniprot_ids):
            selected_orthogroups.append(row['Orthogroup'])

    print(f'Selected orthogroups: {selected_orthogroups}')
    return selected_orthogroups

def graficar_upset_plots_proteome(orthogroups_df, selected_orthogroups, species):
    """Generate UpSet plots for orthogroups and genes specific to the proteome."""
    data = orthogroups_df[orthogroups_df['Orthogroup'].isin(selected_orthogroups)]

    gene_presence = pd.DataFrame(index=data['Orthogroup'])
    total_genes = data.set_index('Orthogroup')

    for sp in species:
        total_genes[sp] = total_genes[sp].str.split(', ').apply(lambda x: len(set(x)) if isinstance(x, list) else 0)
        gene_presence[sp] = total_genes[sp] > 0

    total_genes = total_genes.apply(pd.to_numeric, errors='coerce')
    gene_presence = gene_presence.astype(int)

    memberships = []
    gene_counts = total_genes.sum(axis=1)

    for _, row in gene_presence.iterrows():
        memberships.append([sp for sp in species if row[sp] > 0])

    # Dynamic sizing
    n_species = len(species)
    fig_size = calcular_figsize(n_species)
    elem_size = calcular_element_size(n_species)

    # First plot: orthogroups
    upset_data_groups = from_memberships(memberships)
    fig1 = plt.figure(figsize=fig_size)
    upset1 = UpSet(upset_data_groups, subset_size='count', show_counts=True,
                   sort_by='degree', element_size=elem_size)
    upset1.plot(fig=fig1)

    ax1 = fig1.axes[1]
    ylabels1 = [wrap_label(label.get_text()) for label in ax1.get_yticklabels()]
    ax1.set_yticklabels(ylabels1)

    plt.suptitle('UpSet Plot of Orthogroups (Proteome)', fontsize=16)
    image_path_ortogrupos = os.path.join('static', 'plots', 'upset_plot_ortogrupos.png')
    plt.savefig(image_path_ortogrupos, bbox_inches='tight')
    plt.close(fig1)

    # Second plot: genes
    upset_data_genes = from_memberships(memberships, data=gene_counts)
    fig2 = plt.figure(figsize=fig_size)
    upset2 = UpSet(upset_data_genes, subset_size='sum', show_counts=True,
                   sort_by='degree', element_size=elem_size)
    upset2.plot(fig=fig2)

    ax2 = fig2.axes[1]
    ylabels2 = [wrap_label(label.get_text()) for label in ax2.get_yticklabels()]
    ax2.set_yticklabels(ylabels2)

    plt.suptitle('UpSet Plot of Genes (Proteome)', fontsize=16)
    image_path_genes = os.path.join('static', 'plots', 'upset_plot_genes.png')
    plt.savefig(image_path_genes, bbox_inches='tight')
    plt.close(fig2)

    return 'upset_plot_ortogrupos.png', 'upset_plot_genes.png'

def generar_archivo_excel_upsetplots_filtrado(
    orthogroups_df,
    ortogrupos_por_combinacion,
    species,
    abreviaturas,
    selected_orthogroups,
    filename='UpSetPlot_Filtrado.xlsx'
):
    """
    Generates a filtered Excel file (only selected orthogroups),
    preserving numbered sheet names (01-, 02-, ...) to avoid collisions.
    """

    selected_numeric_ids = [int(re.search(r'\d+', og).group()) for og in selected_orthogroups]

    base_excel = 'UpSetPlot_Data_v2.xlsx'

    combos = []
    for combinacion, ortogrupos in ortogrupos_por_combinacion.items():
        label = (
            ' + '.join([abreviaturas.get(sp, sp) for sp in combinacion])
            if abreviaturas else ' + '.join(list(combinacion))
        )
        label = label or "Unnamed_Combination"
        degree = len(combinacion)
        n_og = len(ortogrupos)
        combos.append((combinacion, ortogrupos, label, degree, n_og))

    combos.sort(key=lambda x: (x[3], -x[4], x[2]))

    with pd.ExcelWriter(base_excel) as writer:
        meta_rows = []

        for i, (combinacion, ortogrupos, label, degree, n_og) in enumerate(combos, start=1):
            combinacion_data = []

            for ortogrupo in ortogrupos:
                row_data = {'Orthogroup ID': ortogrupo}
                for sp in species:
                    if sp in orthogroups_df.columns:
                        proteins = orthogroups_df.at[ortogrupo, sp]
                        row_data[sp] = proteins if pd.notna(proteins) else ""
                combinacion_data.append(row_data)

            df_combinacion = pd.DataFrame(combinacion_data)

            prefix = f"{i:02d}-"
            sheet_name = (prefix + _safe_sheet_label(label))[:31]
            df_combinacion.to_excel(writer, sheet_name=sheet_name, index=False)

            meta_rows.append({
                "index": i,
                "sheet_name": sheet_name,
                "degree": degree,
                "n_orthogroups": n_og,
                "label": label,
                "species_combination": " | ".join(combinacion)
            })

        pd.DataFrame(meta_rows).to_excel(writer, sheet_name="Meta", index=False)

    original_data = pd.read_excel(base_excel, sheet_name=None)

    filtered_sheets = {}
    for sheet_name, df in original_data.items():
        if 'Orthogroup ID' not in df.columns:
            continue
        filtered_df = df[df['Orthogroup ID'].isin(selected_numeric_ids)]
        if not filtered_df.empty:
            filtered_sheets[sheet_name] = filtered_df

    with pd.ExcelWriter(filename) as writer:
        if "Meta" in original_data:
            original_data["Meta"].to_excel(writer, sheet_name="Meta", index=False)

        for sheet_name, df in filtered_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    return filename

def read_orthogroups_data(zip_path):
    """Read and return the contents of the Orthogroups.tsv file from a ZIP archive."""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        with zip_ref.open('Orthogroups.tsv') as file:
            return pd.read_csv(file, sep='\t')


def normalize(text):
    return re.sub(r"[^a-zA-Z0-9]", "", text.lower())

def split_species_name(fullname):
    parts = fullname.split()
    base = " ".join(parts[:2]) if len(parts) >= 2 else fullname
    strain = " ".join(parts[2:]) if len(parts) > 2 else ""
    match = re.search(r"[A-Z][0-9]", fullname)
    if match:
        strain = fullname[match.start():]
    return base.strip(), strain.strip()

def extract_species_names_from_tsv(path):
    df = pd.read_csv(path, sep='\t', nrows=0)
    return list(df.columns[1:])

def load_proteomes(json_path):
    with open(json_path, "r") as f:
        return json.load(f)

def match_species(species_list, proteomes):
    matches = []
    for original in species_list:
        base, strain = split_species_name(original)
        base_norm = normalize(base)
        strain_norm = normalize(strain)
        candidates = [p for p in proteomes if normalize(p["label"]).startswith(base_norm)]
        matched = None
        for c in candidates:
            if strain_norm in normalize(c["label"]):
                matched = c
                break
        matches.append({
            "original": original,
            "base": base,
            "strain": strain,
            "match": matched
        })
    return matches

def generate_go_excel(tsv_path, species_to_goafile, output_excel_path):
    """
    Generates an Excel file with 4 sheets and returns a 'summary' with diagnostics.
    If common issues are detected, raises ValueError with a clear message.
    """
    summary = {
        "tsv_path": tsv_path,
        "output_excel_path": output_excel_path,
        "n_orthogroups": 0,
        "n_species_cols": 0,
        "species_with_goa": sorted(list(species_to_goafile.keys())),
        "species_without_goa": [],
        "rows_zero_annotation": 0,
        "rows_nonzero_annotation": 0,
        "problems": [],
        "warnings": []
    }

    # --- Basic input validation
    if not os.path.exists(tsv_path):
        raise FileNotFoundError(f"Orthogroups.tsv not found at {tsv_path}")
    if not isinstance(species_to_goafile, dict) or not species_to_goafile:
        raise ValueError("species_to_goafile is empty or not a dict")

    # --- Load and check structure
    try:
        df = pd.read_csv(tsv_path, sep='\t')
    except Exception as e:
        raise ValueError(f"Could not read TSV as tab-delimited: {e}")

    if "Orthogroup" not in df.columns:
        raise ValueError("TSV must contain an 'Orthogroup' column as first column")

    species_all = list(df.columns[1:])
    summary["n_orthogroups"] = len(df)
    summary["n_species_cols"] = len(species_all)

    if summary["n_orthogroups"] == 0:
        summary["warnings"].append("TSV has 0 rows (no orthogroups).")

    # --- Detect TSV species without GOA and extra GOA species not in TSV
    tsv_species_set = set(species_all)
    goa_species_set = set(species_to_goafile.keys())
    missing_goa_for_tsv_species = sorted([s for s in species_all if s not in goa_species_set])
    extra_goa_species_not_in_tsv = sorted(list(goa_species_set - tsv_species_set))

    summary["species_without_goa"] = missing_goa_for_tsv_species
    if missing_goa_for_tsv_species:
        summary["warnings"].append(
            f"{len(missing_goa_for_tsv_species)} TSV species have no GOA mapping (ok, they will remain in 'Initial Groups')."
        )
    if extra_goa_species_not_in_tsv:
        summary["warnings"].append(
            f"{len(extra_goa_species_not_in_tsv)} GOA species not found as TSV columns: {extra_goa_species_not_in_tsv[:5]}..."
        )

    # --- Robust calculation of annotation percentage
    porcentajes = []
    # Precompile split pattern: comma + optional spaces
    splitter = re.compile(r"\s*,\s*")

    for _, row in df.iterrows():
        total_proteinas = 0
        proteinas_con_goa = 0

        for sp in species_all:
            val = row.get(sp)
            if pd.isna(val):
                continue
            s = str(val).strip()
            if not s:
                continue

            # Robust split: accepts both "A|X, B|Y" and "A|X,B|Y"
            prots = [p for p in splitter.split(s) if p]
            total_proteinas += len(prots)

            # Only species with GOA mapping count toward the numerator
            if sp in goa_species_set:
                proteinas_con_goa += len(prots)

        pct = (proteinas_con_goa / total_proteinas * 100.0) if total_proteinas > 0 else 0.0
        porcentajes.append(pct)

    df.insert(1, "Annotation Percentage", porcentajes)

    # --- Split into sheets
    initial = df.copy()
    filtered = df[df["Annotation Percentage"] > 0].copy()
    removed  = df[df["Annotation Percentage"] == 0].copy()

    summary["rows_zero_annotation"] = len(removed)
    summary["rows_nonzero_annotation"] = len(filtered)

    # 'Groups of Interest' = only columns with GOA (missing ones are not errors)
    species_with_goa_sorted = sorted(list(goa_species_set & tsv_species_set))
    columns_interest = ["Orthogroup", "Annotation Percentage"] + species_with_goa_sorted
    interest = initial[columns_interest].copy()

    # --- Save Excel with a 'Meta' sheet (diagnostics)
    try:
        with pd.ExcelWriter(output_excel_path) as writer:
            # Diagnostic sheet
            meta = pd.DataFrame({
                "key": [
                    "n_orthogroups", "n_species_cols",
                    "rows_nonzero_annotation", "rows_zero_annotation"
                ],
                "value": [
                    summary["n_orthogroups"],
                    summary["n_species_cols"],
                    summary["rows_nonzero_annotation"],
                    summary["rows_zero_annotation"]
                ]
            })
            meta.to_excel(writer, sheet_name="Meta", index=False)

            initial.to_excel(writer, sheet_name="Initial Groups", index=False)
            filtered.to_excel(writer, sheet_name="Filtered Groups", index=False)
            removed.to_excel(writer, sheet_name="Removed Groups", index=False)
            interest.to_excel(writer, sheet_name="Groups of Interest", index=False)

            # Sheet with species and GOA mappings (audit)
            m = pd.DataFrame(
                [{"species": s, "goa_file": species_to_goafile.get(s, "")} for s in species_all]
            )
            m.to_excel(writer, sheet_name="Species & GOA Map", index=False)
    except Exception as e:
        raise ValueError(f"Failed to write Excel: {e}")

    # --- Useful logs
    print(f"✅ GOA Excel saved to {output_excel_path}")
    print(f"🧬 Species (TSV) with GOA: {len(species_with_goa_sorted)} / {len(species_all)}")
    if missing_goa_for_tsv_species:
        print(f"⚠️ Missing GOA (TSV): {missing_goa_for_tsv_species[:8]}{'...' if len(missing_goa_for_tsv_species)>8 else ''}")
    if extra_goa_species_not_in_tsv:
        print(f"⚠️ Extra GOA (not in TSV): {extra_goa_species_not_in_tsv[:8]}{'...' if len(extra_goa_species_not_in_tsv)>8 else ''}")

    return summary

def generate_go_image_from_excel(excel_path, output_image_path):
    """Generates a 4-panel figure using the annotation percentages already calculated in the Excel file."""
    try:
        df = pd.read_excel(excel_path, sheet_name="Initial Groups")
        if "Annotation Percentage" not in df.columns:
            print("❌ The sheet does not contain the 'Annotation Percentage' column")
            return

        all_annotation = df["Annotation Percentage"]
        non_zero_annotation = all_annotation[all_annotation > 0]
        bins = range(0, 101, 10)

        fig, axes = plt.subplots(2, 2, figsize=(18, 16))

        # a) Boxplot All
        sns.boxplot(y=all_annotation, color="skyblue", ax=axes[0, 0])
        axes[0, 0].set_title("a) All Orthogroups", fontsize=16)
        axes[0, 0].set_ylabel("Annotation %")
        median_all = all_annotation.median()
        q1_all = all_annotation.quantile(0.25)
        q3_all = all_annotation.quantile(0.75)
        axes[0, 0].axhline(median_all, color="orange", linestyle="--", label=f"Median: {median_all:.2f}%")
        axes[0, 0].axhline(q1_all, color="green", linestyle="--", label=f"Q1: {q1_all:.2f}%")
        axes[0, 0].axhline(q3_all, color="purple", linestyle="--", label=f"Q3: {q3_all:.2f}%")
        axes[0, 0].legend()

        # b) Boxplot >0%
        sns.boxplot(y=non_zero_annotation, color="lightgreen", ax=axes[0, 1])
        axes[0, 1].set_title("b) Orthogroups with >0% Annotation", fontsize=16)
        axes[0, 1].set_ylabel("Annotation %")
        median_nz = non_zero_annotation.median()
        q1_nz = non_zero_annotation.quantile(0.25)
        q3_nz = non_zero_annotation.quantile(0.75)
        axes[0, 1].axhline(median_nz, color="orange", linestyle="--", label=f"Median: {median_nz:.2f}%")
        axes[0, 1].axhline(q1_nz, color="green", linestyle="--", label=f"Q1: {q1_nz:.2f}%")
        axes[0, 1].axhline(q3_nz, color="purple", linestyle="--", label=f"Q3: {q3_nz:.2f}%")
        axes[0, 1].legend()

        # c) Histogram All
        sns.histplot(all_annotation, bins=bins, color="cornflowerblue", kde=True, edgecolor="black", ax=axes[1, 0])
        axes[1, 0].set_title("c) Distribution - All Orthogroups")
        axes[1, 0].set_xlabel("Annotation %")
        axes[1, 0].set_ylabel("Number of Orthogroups")

        # d) Histogram >0%
        sns.histplot(non_zero_annotation, bins=bins, color="lightgreen", kde=True, edgecolor="black", ax=axes[1, 1])
        axes[1, 1].set_title("d) Distribution - Orthogroups >0%")
        axes[1, 1].set_xlabel("Annotation %")
        axes[1, 1].set_ylabel("Number of Orthogroups")

        plt.tight_layout()
        fig.savefig(output_image_path)
        plt.close()
        print(f"✅ GO image generated at {output_image_path}")

    except Exception as e:
        print(f"❌ Error generating GO figure from Excel: {e}")

def clear_goa_dir(goa_dir: str):
    """Cleans the GOA directory by removing all its contents (files and subdirectories)."""
    p = Path(goa_dir)
    p.mkdir(parents=True, exist_ok=True)
    for item in p.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                try:
                    item.unlink()
                except FileNotFoundError:
                    pass
        except Exception as e:
            print(f"[WARN] Could not delete {item}: {e}")


def parse_uniprot_block(text_or_list) -> List[str]:
    if text_or_list is None:
        return []
    if isinstance(text_or_list, list):
        raw = " ".join(map(str, text_or_list))
    else:
        raw = str(text_or_list)
    import re
    parts = re.split(r"[\s,;]+", raw.strip())
    return [p for p in (x.strip() for x in parts) if p]

def build_id2gos_from_goa_folder(goa_folder: str,
                                 limit_files: Optional[List[str]] = None
                                 ) -> Dict[str, List[str]]:
    """
    Reads ALL .goa/.gaf (including .gz) files from the folder and builds id2gos (BP+CC+MF).
    If limit_files is provided, restricts to that subset of files (by name).
    Returns: dict[gene_id] -> list[go_id]
    """
    folder = Path(goa_folder)
    if not folder.exists():
        raise FileNotFoundError(f"GOA folder not found: {goa_folder}")

    # Accept .goa/.gaf with or without .gz
    patterns = ["*.goa", "*.gaf", "*.goa.gz", "*.gaf.gz"]
    files: List[Path] = []
    for pat in patterns:
        files.extend(folder.glob(pat))
    files = sorted(files)

    if limit_files:
        limit_set = set(limit_files)
        files = [f for f in files if f.name in limit_set]

    if not files:
        raise FileNotFoundError("No GOA/GAF files found in GOA folder.")

    id2gos = defaultdict(set)  # gene -> set(GO)
    ns_totals = {"BP": 0, "CC": 0, "MF": 0}
    total_read = 0

    for f in files:
        try:
            print(f"HMS:{datetime.timedelta(0)}  reading annotations: {f.name}", flush=True)

            # GafReader supports .gz and allows filtering by namespace
            gafr = GafReader(str(f), prt=None)

            per_file_counts = {"BP": 0, "CC": 0, "MF": 0}
            for ns in ("BP", "CC", "MF"):
                d_ns = gafr.get_id2gos(namespace=ns)  # dict[str, set[str]]
                # count terms per file/namespace (for logging)
                per_file_counts[ns] = sum(len(gos) for gos in d_ns.values())
                # merge into global structure
                for gid, gos in d_ns.items():
                    id2gos[str(gid)].update(gos)

            total_read += 1
            for k in ns_totals:
                ns_totals[k] += per_file_counts[k]

            print(f"{per_file_counts['BP']} GO in BP, "
                  f"{per_file_counts['CC']} in CC, "
                  f"{per_file_counts['MF']} in MF", flush=True)

        except Exception as e:
            print(f"[WARN] Could not read {f.name}: {e}", flush=True)

    if total_read == 0:
        raise ValueError("No GO annotations could be read from the .goa/.gaf files.")

    print(f"TOTAL files read: {total_read}. "
          f"Loaded GO -> BP:{ns_totals['BP']}, CC:{ns_totals['CC']}, MF:{ns_totals['MF']}",
          flush=True)

    # Convert sets to lists (stable/serializable). Sort if needed for reproducibility.
    return {gid: sorted(gos) for gid, gos in id2gos.items()}

def ensure_godag(path=GO_ROOT_OBO):
    """Ensures that the GO DAG (ontology) file exists and loads it."""
    if not Path(path).exists():
        raise FileNotFoundError(f"Cannot find OBO file at {path}. It must be located next to app.py.")
    print(f"[INFO] Loading GODag from {path} ...", flush=True)
    return GODag(path, prt=None)


############################################################################################################
############################################################################################################
###############################################   @APP ROUTE     ###########################################
############################################################################################################
############################################################################################################

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/reanalyze')
def reanalyze():
    """Redirects to the point where Figures 1 and 2 were generated."""
    # If the figures have already been generated, redirect the user to that view
    if 'figuras_generadas' in session:
        plot_url_1 = session['plot_url_1']
        plot_url_2 = session['plot_url_2']
        ruta_carpeta = session.get('ruta_carpeta', '')
        species = list(session.get('species', []))  # Retrieve species from the dataframe
        return render_template('resultado.html', 
                               plot_url_1=plot_url_1, 
                               plot_url_2=plot_url_2, 
                               species=species, 
                               ruta_carpeta=ruta_carpeta)
    # If no data exists, redirect to the home page
    return redirect(url_for('index'))

import os, zipfile, shutil
from flask import flash, redirect, url_for, render_template, request, session

@app.route('/cargar_carpeta', methods=['POST', 'GET'])
def cargar_carpeta():
    """
    Supported inputs:
      - POST + file (mode=upload): ZIP uploaded -> extracted into static/data_folder/upload
      - POST + mode=generated:     uses Proteomas/Orthogroups.zip -> extracted into static/data_folder/generated
      - GET  + filename=Orthogroups.zip (&mode=preselected|generated):
                                    preselected = static/Orthogroups.zip
                                    generated   = Proteomas/Orthogroups.zip
      - POST + especies[]=...      (from resultado.html) generates Figures 4 and 5
    """
    global orthogroups_df, gene_count_df, species_selected, ortogrupos_por_combinacion, abreviaturas

    def _clean_dir(path: str):
        os.makedirs(path, exist_ok=True)
        for entry in os.listdir(path):
            p = os.path.join(path, entry)
            try:
                if os.path.isfile(p) or os.path.islink(p):
                    os.unlink(p)
                elif os.path.isdir(p):
                    shutil.rmtree(p)
            except Exception as e:
                print(f"[WARN] Could not delete {p}: {e}")

    def _render_result_and_cache(ruta_carpeta, modo_flag):
        """
        Loads DataFrames, generates Figures 1 and 2, stores results in session, and renders resultado.html.
        Minimum requirements: Orthogroups.GeneCount.tsv and Orthogroups.tsv
        (SingleCopy and Unassigned files are optional for Figures 1 and 2).
        """
        try:
            # Log for debugging
            try:
                print(f"[INFO] Contents of '{ruta_carpeta}':", os.listdir(ruta_carpeta))
            except Exception as _e:
                print(f"[WARN] Could not list '{ruta_carpeta}': {_e}")

            # --- Minimum required files
            req_gene = os.path.join(ruta_carpeta, 'Orthogroups.GeneCount.tsv')
            req_og   = os.path.join(ruta_carpeta, 'Orthogroups.tsv')
            missing = [p for p in (req_gene, req_og) if not os.path.exists(p)]
            if missing:
                for p in missing:
                    print(f"[ERROR] Missing: {p}")
                flash("Missing required files (Orthogroups.GeneCount.tsv and Orthogroups.tsv are mandatory).")
                return redirect(url_for('index'))

            # --- Optional files warning (continue even if missing)
            for opt in ('Orthogroups_SingleCopyOrthologues.txt',
                        'Orthogroups_UnassignedGenes.tsv',
                        'Orthogroups.txt'):
                p = os.path.join(ruta_carpeta, opt)
                if not os.path.exists(p):
                    print(f"[WARN] Optional file not found (continuing): {p}")

            # Load and generate figures
            gene_count_df_, orthogroups_df_, single_copy_df_, unassigned_df_ = cargar_datos_carpeta(ruta_carpeta)

            plot_url_1 = generar_figura_1(gene_count_df_)
            plot_url_2 = generar_figura_2(gene_count_df_)

            # Cache results in session
            session['figuras_generadas'] = True
            session['plot_url_1'] = plot_url_1
            session['plot_url_2'] = plot_url_2
            session['ruta_carpeta'] = ruta_carpeta
            session['species'] = list(gene_count_df_.columns[1:])
            session['modo'] = modo_flag

            # Optionally keep globals if used elsewhere
            globals()['gene_count_df'] = gene_count_df_
            globals()['orthogroups_df'] = orthogroups_df_

            return render_template(
                'resultado.html',
                plot_url_1=plot_url_1,
                plot_url_2=plot_url_2,
                species=list(gene_count_df_.columns[1:]),
                ruta_carpeta=ruta_carpeta
            )

        except Exception as e:
            print(f"[ERROR] _render_result_and_cache(mode={modo_flag}, path={ruta_carpeta}) -> {e}")
            flash(f"Error preparing results ({modo_flag}): {e}")
            return redirect(url_for('index'))

    # -------------------------
    # POST
    # -------------------------
    if request.method == 'POST':

        # --- A) UPLOAD: manually uploaded ZIP file
        if 'file' in request.files:
            folder = request.files['file']
            if folder.filename == '':
                flash('No ZIP file selected.')
                return redirect(url_for('index'))
            if not folder.filename.lower().endswith('.zip'):
                flash('The uploaded file must be a .zip archive.')
                return redirect(url_for('index'))

            ruta_carpeta = os.path.join('static', 'data_folder', 'upload')
            _clean_dir(ruta_carpeta)

            zip_path = os.path.join(ruta_carpeta, folder.filename)
            folder.save(zip_path)

            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(ruta_carpeta)
            except Exception as e:
                print(f"[ERROR] Unzipping uploaded ZIP: {e}")
                flash(f"Error extracting the uploaded ZIP: {e}")
                return redirect(url_for('index'))

            return _render_result_and_cache(ruta_carpeta, 'upload')

        # --- B) GENERATED: ZIP generated by OrthoFinder
        if request.form.get('modo') == 'generated':
            ruta_carpeta = os.path.join('static', 'data_folder', 'generated')
            _clean_dir(ruta_carpeta)

            zip_src = os.path.join('Proteomas', 'Orthogroups.zip')
            if not os.path.isfile(zip_src):
                flash('File Proteomas/Orthogroups.zip not found. Please run OrthoFinder first.')
                return redirect(url_for('index'))

            try:
                with zipfile.ZipFile(zip_src, 'r') as zip_ref:
                    zip_ref.extractall(ruta_carpeta)
            except Exception as e:
                print(f"[ERROR] Unzipping generated ZIP: {e}")
                flash(f"Error extracting generated ZIP: {e}")
                return redirect(url_for('index'))

            return _render_result_and_cache(ruta_carpeta, 'generated')

        # --- C) Additional figures (species selection)
        if 'especies' in request.form:
            species_selected = request.form.getlist('especies')
            ruta_carpeta = request.form.get('ruta_carpeta', session.get('ruta_carpeta', ''))
            if not species_selected:
                flash('Please select at least one species.')
                return redirect(url_for('index'))

            try:
                gene_count_df_, orthogroups_df_, _, _ = cargar_datos_carpeta(ruta_carpeta)
                globals()['gene_count_df'] = gene_count_df_
                globals()['orthogroups_df'] = orthogroups_df_

                abreviaturas = {}
                img_path_3 = None
                img_path_4, ortogrupos_por_combinacion = crear_upset_plot_ortogrupos(
                    gene_count_df_, species_selected, 'UpSet Plot of All Orthogroups'
                )
                img_path_5, _ = crear_upset_plot_proteinas(
                    gene_count_df_, species_selected, 'UpSet Plot of All Proteins', ortogrupos_por_combinacion
                )

                return render_template(
                    'figuras_adicionales.html',
                    img_path_3=img_path_3,
                    img_path_4=img_path_4,
                    img_path_5=img_path_5
                )
            except Exception as e:
                print(f"[ERROR] Additional figures: {e}")
                flash(f"Error generating additional figures: {e}")
                return redirect(url_for('index'))

    # -------------------------
    # GET (preselected / generated / upload)
    # -------------------------
    if request.method == 'GET':
        # A) preselected / generated -> extract from given ZIP
        if request.args.get('filename') == 'Orthogroups.zip':
            modo_arg = request.args.get('modo', 'preselected')
            try:
                if modo_arg == 'generated':
                    zip_src = os.path.join('Proteomas', 'Orthogroups.zip')
                    ruta_carpeta = os.path.join('static', 'data_folder', 'generated')
                else:
                    zip_src = os.path.join('static', 'Orthogroups.zip')
                    ruta_carpeta = os.path.join('static', 'data_folder')

                _clean_dir(ruta_carpeta)

                with zipfile.ZipFile(zip_src, 'r') as zip_ref:
                    zip_ref.extractall(ruta_carpeta)

                return _render_result_and_cache(ruta_carpeta, modo_arg)

            except Exception as e:
                print(f"[ERROR] GET cargar_carpeta (mode={modo_arg}): {e}")
                flash(f"Error processing file (mode={modo_arg}): {e}")
                return redirect(url_for('index'))

        # B) upload -> reuse already extracted folder from upload flow
        if request.args.get('modo') == 'upload':
            try:
                ruta_carpeta = os.path.join('static', 'data_folder', 'upload')
                if not os.path.isdir(ruta_carpeta):
                    flash('No upload data prepared. Please upload a ZIP first.')
                    return redirect(url_for('index'))

                # Do not clean or extract anything here: it’s already unpacked by the upload POST
                return _render_result_and_cache(ruta_carpeta, 'upload')

            except Exception as e:
                print(f"[ERROR] GET cargar_carpeta (mode=upload): {e}")
                flash(f"Error preparing upload: {e}")
                return redirect(url_for('index'))

    # -------------------------
    # Re-render if figures already exist
    # -------------------------
    if session.get('figuras_generadas'):
        return render_template(
            'resultado.html',
            plot_url_1=session.get('plot_url_1'),
            plot_url_2=session.get('plot_url_2'),
            species=session.get('species', []),
            ruta_carpeta=session.get('ruta_carpeta', '')
        )

    return redirect(url_for('index'))

@app.route('/create_excel')
def create_excel():
    """Generate the Excel file when requested via the button."""
    global orthogroups_df, species_selected, gene_count_df, ortogrupos_por_combinacion, abreviaturas

    # Check if the data is loaded; if not, load it
    if orthogroups_df is None:
        gene_count_df, orthogroups_df, _, _ = cargar_datos_carpeta('static/data_folder')

    # Create the Excel file
    excel_filename = generar_archivo_excel_upsetplots_v2(ortogrupos_por_combinacion, orthogroups_df, species_selected, abreviaturas)

    return 'Excel generated'

@app.route('/download_excel')
def download_excel():
    excel_path = 'UpSetPlot_Data_v2.xlsx'
    return send_file(excel_path, as_attachment=True)

@app.route('/download/<filename>')
def download_image(filename):
    return send_file(os.path.join('static', 'plots', filename), as_attachment=True)

@app.route('/generate_new_figures', methods=['POST'])
def generate_new_figures():
    global orthogroups_df, species_selected, ortogrupos_por_combinacion, selected_orthogroups  # Add selected_orthogroups as global

    # Get UniProt IDs sent from the frontend
    data = request.get_json()
    uniprot_ids = data.get('data', '').split()

    # Filter orthogroups using the provided UniProt IDs
    selected_orthogroups = filter_orthogroups(orthogroups_df, uniprot_ids)

    if selected_orthogroups:
        # Generate filtered figures (Figures 6 and 7)
        img_path_ortogrupos, img_path_genes = graficar_upset_plots_proteome(
            orthogroups_df, selected_orthogroups, species_selected
        )

        # Return figure paths to the frontend
        return jsonify({'img_path_6': img_path_ortogrupos, 'img_path_7': img_path_genes})
    else:
        return jsonify({'error': 'No orthogroups found matching the provided UniProt IDs.'}), 400

@app.route('/create_excel_proteome_filtrado', methods=['POST'])
def create_excel_proteome_filtrado():
    global orthogroups_df, ortogrupos_por_combinacion, species_selected, abreviaturas, selected_orthogroups

    # Check that selected_orthogroups has already been generated
    if not selected_orthogroups:
        return jsonify({'error': 'No filtered orthogroups have been generated yet.'}), 400

    # Generate the Excel file using the selected_orthogroups
    excel_filename = generar_archivo_excel_upsetplots_filtrado(
        orthogroups_df, ortogrupos_por_combinacion, species_selected, abreviaturas, selected_orthogroups
   )

    return send_file(excel_filename, as_attachment=True)

@app.route("/1-seleccion_especies")
def seleccion_especies():
    return render_template("1-seleccion_especies.html")

@app.route("/download", methods=["POST"])
def download_proteomes():
    proteome_ids = request.json.get("proteome_ids", [])

    if not proteome_ids:
        print("❌ No proteomes received from frontend.")
        return jsonify({"error": "No proteomes provided."}), 400

    print("🔁 Cleaning Proteomes folder...")
    for f in os.listdir(PROTEOMES_FOLDER):
        path = os.path.join(PROTEOMES_FOLDER, f)
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except Exception as e:
            print(f"❌ Error deleting {path}: {e}")

    descargados = []
    errores = []
    vacios = []

    for pid in proteome_ids:
        print(f"\n🔍 Processing {pid}...")

        # METADATA
        url_metadata = f"https://rest.uniprot.org/proteomes/{pid}"
        try:
            r_meta = requests.get(url_metadata)
            if r_meta.status_code != 200:
                raise Exception(f"Metadata HTTP {r_meta.status_code}")
            metadata = r_meta.json()
        except Exception as e:
            print(f"❌ Failed to download metadata for {pid}: {e}")
            errores.append(f"{pid} (metadata failed: {e})")
            continue

        # File name
        organism_name = metadata.get("taxonomy", {}).get("scientificName", "Unknown_organism")
        safe_name = re.sub(r"[^\w\-_\.() ]", "_", organism_name).replace(" ", "_")
        filename = f"{safe_name}.fasta"
        filepath = os.path.join(PROTEOMES_FOLDER, filename)

        # FASTA
        fasta_url = f"https://rest.uniprot.org/uniprotkb/stream?format=fasta&compressed=false&query=(proteome:{pid})"
        try:
            r_fasta = requests.get(fasta_url)
            if r_fasta.status_code != 200:
                raise Exception(f"FASTA HTTP {r_fasta.status_code}")
            with open(filepath, "w") as f:
                f.write(r_fasta.text)
            print(f"📁 Saved to: {filepath}")
        except Exception as e:
            print(f"❌ Failed to save FASTA for {pid}: {e}")
            errores.append(f"{pid} (fasta failed: {e})")
            continue

        # Size verification
        if os.path.getsize(filepath) == 0:
            os.remove(filepath)
            print(f"⚠️ Empty file removed: {filename}")
            vacios.append(filename)
        else:
            descargados.append(filename)

    print("\n✅ DOWNLOAD COMPLETED")
    print(f"✔️ Downloaded: {descargados}")
    print(f"⚠️ Empty: {vacios}")
    print(f"❌ Errors: {errores}")

    return jsonify({
        "descargados": descargados,
        "vacios": vacios,
        "errores": errores
    })

@app.route("/run_orthofinder", methods=["POST"])
def run_orthofinder():
    import time
    import traceback
    import zipfile
    import os

    start_time = time.time()

    try:
        process = subprocess.Popen(
            ["orthofinder", "-f", PROTEOMES_FOLDER, "-t", "8", "-a", "8", "-og"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        log_lines = []
        for line in iter(process.stdout.readline, ''):
            print(line.strip())
            log_lines.append(line.strip())

        process.stdout.close()
        process.wait()

        if process.returncode != 0:
            return jsonify({
                "error": "OrthoFinder failed.",
                "log": "\n".join(log_lines)
            }), 500

        resultados_base = os.path.join(PROTEOMES_FOLDER, "OrthoFinder")
        subdirs = [d for d in os.listdir(resultados_base) if d.startswith("Results_")]
        if not subdirs:
            return jsonify({"error": "❌ No 'Results_' folder found"}), 500

        latest_result = sorted(subdirs)[-1]
        orthogroups_path = os.path.join(resultados_base, latest_result, "Orthogroups")

        files_to_zip = [
            "Orthogroups.tsv",
            "Orthogroups.txt",
            "Orthogroups.GeneCount.tsv",
            "Orthogroups_UnassignedGenes.tsv"
        ]

        zip_path = os.path.join(PROTEOMES_FOLDER, "Orthogroups.zip")
        if os.path.exists(zip_path):
            os.remove(zip_path)

        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for filename in files_to_zip:
                file_path = os.path.join(orthogroups_path, filename)
                if os.path.exists(file_path):
                    zipf.write(file_path, arcname=filename)
                else:
                    print(f"⚠️ Not found: {filename}")

        end_time = time.time()
        tiempo = f"⏱️ Total time: {int((end_time - start_time) // 60)}m {int((end_time - start_time) % 60)}s"

        return jsonify({
            "status": "OrthoFinder (orthogroups only) completed successfully ✅",
            "log": "\n".join(log_lines),
            "time": tiempo
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Unexpected error: {e}"}), 500

@app.route('/stream_orthofinder')
def stream_orthofinder():
    import zipfile
    import os

    def generate():
        process = subprocess.Popen(
            ["orthofinder", "-f", PROTEOMES_FOLDER, "-t", "8", "-a", "8", "-og"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        for line in iter(process.stdout.readline, ''):
            yield f"data: {line.strip()}\n\n"

        process.stdout.close()
        process.wait()

        resultados_base = os.path.join(PROTEOMES_FOLDER, "OrthoFinder")
        subdirs = [d for d in os.listdir(resultados_base) if d.startswith("Results_")]
        if not subdirs:
            yield "data: ❌ No 'Results_' folder found.\n\n"
            yield "data: DONE\n\n"
            return

        latest_result = sorted(subdirs)[-1]
        orthogroups_path = os.path.join(resultados_base, latest_result, "Orthogroups")

        files_to_zip = [
            "Orthogroups.tsv",
            "Orthogroups.txt",
            "Orthogroups.GeneCount.tsv",
            "Orthogroups_UnassignedGenes.tsv"
        ]

        zip_path = os.path.join(PROTEOMES_FOLDER, "Orthogroups.zip")
        if os.path.exists(zip_path):
            os.remove(zip_path)

        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for filename in files_to_zip:
                file_path = os.path.join(orthogroups_path, filename)
                if os.path.exists(file_path):
                    zipf.write(file_path, arcname=filename)
                    yield f"data: ✔️ Added to ZIP: {filename}\n\n"
                else:
                    yield f"data: ⚠️ Missing file: {filename}\n\n"

        yield "data: ✅ OrthoFinder completed successfully. ZIP created at Proteomas/Orthogroups.zip\n\n"
        yield "data: DONE\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/generate_tree_image', methods=['POST'])
def generate_tree_image():
    from ete3 import NCBITaxa, TreeStyle, TextFace, faces
    import random
    import json

    species_labels = request.form.getlist('especies')  # exact selected labels
    if not species_labels:
        return jsonify({"error": "No species selected"}), 400

    with open("static/Proteomes_json/proteomes_list.json") as f:
        proteomes = json.load(f)

    especies_elegidas = [p for p in proteomes if p['label'] in species_labels]
    taxon_ids = [int(p["taxon_id"]) for p in especies_elegidas if p["taxon_id"].isdigit()]
    taxid_to_label = {int(p["taxon_id"]): p["label"] for p in especies_elegidas if p["taxon_id"].isdigit()}

    if not taxon_ids:
        return jsonify({"error": "Invalid taxon IDs"}), 400

    ncbi = NCBITaxa()
    tree = ncbi.get_topology(taxon_ids)

    # Randomize branch lengths to improve visualization
    for node in tree.traverse():
        if not node.is_root():
            node.dist = round(random.uniform(0.1, 1.5), 3)

    # Define layout for branch labels
    def layout(node):
        if node.is_leaf():
            label = taxid_to_label.get(int(node.name), f"taxid {node.name}")
            short_label = label if len(label) <= 50 else label[:47] + "..."
            face = TextFace(short_label, fsize=11, fgcolor="black", fstyle="italic")
            face.margin_left = 4
            faces.add_face_to_node(face, node, column=0, position="branch-right")

    # Tree visualization style
    ts = TreeStyle()
    ts.layout_fn = layout
    ts.show_leaf_name = False
    ts.mode = "r"
    ts.force_topology = False
    ts.branch_vertical_margin = 15
    ts.scale = 80
    ts.show_scale = False
    ts.title.add_face(TextFace("Phylogenetic Tree", fsize=14, fstyle="bold"), column=0)

    output_path = os.path.join("static", "plots", "tree_labels_at_branch_end.png")
    tree.render(output_path, w=1200, tree_style=ts)
    tree.write(outfile=os.path.join("static", "plots", "tree_labels_at_branch_end.nw"), format=1)

    return jsonify({
        "tree_image_path": "plots/tree_labels_at_branch_end.png"
    })

@app.route('/resultado_goa')
def resultado_goa():
    modo = session.get("modo")
    species = None

    # Prefer using the species list already stored in session if available
    if session.get("species"):
        species = session["species"]

    if species is None:
        # Load species according to mode
        if modo == "preselected":
            zip_path = os.path.join("static", "Orthogroups.zip")
            if not os.path.exists(zip_path):
                return "Expected ZIP file not found (preselected).", 400
            with zipfile.ZipFile(zip_path, 'r') as z:
                with z.open("Orthogroups.tsv") as f:
                    df = pd.read_csv(f, sep="\t", nrows=0)
                    species = list(df.columns[1:])

        elif modo == "generated":
            zip_path = os.path.join("Proteomas", "Orthogroups.zip")
            if not os.path.exists(zip_path):
                return "Expected ZIP file not found (generated).", 400
            with zipfile.ZipFile(zip_path, 'r') as z:
                with z.open("Orthogroups.tsv") as f:
                    df = pd.read_csv(f, sep="\t", nrows=0)
                    species = list(df.columns[1:])

        elif modo == "upload":
            ruta_carpeta = session.get("ruta_carpeta", "")
            if not ruta_carpeta:
                return "No working directory found for upload mode. Please upload the ZIP first.", 400
            tsv_path = os.path.join(ruta_carpeta, "Orthogroups.tsv")
            if not os.path.exists(tsv_path):
                return "Orthogroups.tsv not found in upload directory.", 400
            df = pd.read_csv(tsv_path, sep="\t", nrows=0)
            species = list(df.columns[1:])

        else:
            return "Unrecognized mode. Please ensure you have loaded a valid file.", 400

    # Load available proteomes (with GOA or from the general JSON)
    proteomes = load_proteomes(JSON_PATH)

    # Automatic species matching
    species_cache = match_species(species, proteomes)

    # Save information in session
    session["species_detected"] = species
    session["species_matches"] = species_cache

    return render_template("resultado_goa.html", results=species_cache)

@app.route("/download_goa_files", methods=["POST"])
def download_goa_files():
    """
    Downloads the selected GOA files from the matching table,
    clears GOAfiles/, saves the species->file mapping in session,
    and generates the Excel file 'Gene_Ontology_Analysis.xlsx'.
    """
    try:
        data = request.get_json(silent=True) or {}
        species_to_url = data.get("species_to_url", {})

        if not species_to_url:
            urls = data.get("urls", [])
            if urls:
                return respond(False, "Missing species_to_url mapping",
                               where="download_goa_files",
                               hint="Send species_to_url: { 'Species name': 'https://.../file.goa' }",
                               code=400)
            return respond(False, "No GOA URLs received",
                           where="download_goa_files",
                           hint="Select species with valid GOA and try again.",
                           code=400)

        # 1) Clean GOAfiles/
        print("[INFO] download_goa_files: cleaning GOAfiles/")
        clear_goa_dir(GOA_DOWNLOAD_FOLDER)
        os.makedirs(GOA_DOWNLOAD_FOLDER, exist_ok=True)

        MAX_RETRIES, RETRY_DELAY = 5, 5
        downloaded, existed, failed = [], [], []
        goa_mapping = {}

        for species, url in species_to_url.items():
            try:
                if not url or not isinstance(url, str):
                    failed.append({"species": species, "reason": "Empty or invalid URL"})
                    continue
                filename = url.split("/")[-1] or f"{normalize(species)}.goa"
                outpath = os.path.join(GOA_DOWNLOAD_FOLDER, filename)

                ok = False
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        r = requests.get(url, timeout=30)
                        r.raise_for_status()
                        with open(outpath, "wb") as f:
                            f.write(r.content)
                        ok = True
                        break
                    except Exception as e:
                        print(f"[WARN] failed downloading {url} ({attempt}/{MAX_RETRIES}): {e}")
                        if attempt < MAX_RETRIES:
                            time.sleep(RETRY_DELAY)
                if ok:
                    downloaded.append(filename)
                    goa_mapping[species] = filename
                else:
                    failed.append({"species": species, "reason": "max retries exceeded"})

            except Exception as e:
                failed.append({"species": species, "reason": f"Unexpected: {e}"})

        session["goa_mapping"] = goa_mapping

        # 2) Generate base Excel
        ruta_carpeta = session.get('ruta_carpeta')
        if not ruta_carpeta or not os.path.exists(ruta_carpeta):
            return respond(False, "Working directory not prepared",
                           where="download_goa_files",
                           hint="Reload orthogroups (Upload/Preselected/Generated).",
                           code=400)

        orthogroups_path = os.path.join(ruta_carpeta, 'Orthogroups.tsv')
        if not os.path.exists(orthogroups_path):
            return respond(False, "Orthogroups.tsv not found",
                           where="download_goa_files",
                           hint="Make sure orthogroups were loaded correctly.",
                           code=404)

        os.makedirs(RESULTS_FOLDER, exist_ok=True)
        output_excel = os.path.join(RESULTS_FOLDER, 'Gene_Ontology_Analysis.xlsx')
        excel_summary = generate_go_excel(orthogroups_path, goa_mapping, output_excel)

        print("✅ GOA Excel saved at", output_excel)
        print(f"🧬 Species (TSV) with GOA: {len(excel_summary.get('species_with_goa', []))} / {excel_summary.get('n_species_cols')}")
        if excel_summary.get("species_without_goa"):
            arr = excel_summary["species_without_goa"]
            print(f"⚠️ Without GOA (TSV): {arr[:8]}{'...' if len(arr)>8 else ''}")

        return respond(True, "GOA files processed and Excel generated",
                       where="download_goa_files",
                       payload={
                           "downloaded": downloaded,
                           "failed": failed,
                           "goa_mapping": goa_mapping,
                           "excel_file_path": "download_go_excel",
                           "excel_summary": excel_summary
                       })

    except Exception as e:
        return respond(False, f"Unexpected error in download_goa_files: {e}",
                       where="download_goa_files",
                       hint="Check the log and verify species_to_url, write permissions, and network connection.",
                       code=500)

@app.route("/download_go_excel")
def download_go_excel():
    output_excel_path = os.path.join(RESULTS_FOLDER, "Gene_Ontology_Analysis.xlsx")
    if not os.path.exists(output_excel_path):
        return "The Excel file does not exist. Please run the GO analysis first.", 404
    return send_file(output_excel_path, as_attachment=True)

@app.route("/fix_taxid", methods=["POST"])
def fix_taxid():
    try:
        data = request.get_json(silent=True) or {}
        taxon_id = data.get("taxon_id")
        original = data.get("original")

        if not taxon_id or not original:
            return respond(False, "Missing taxon_id or original name",
                           where="fix_taxid",
                           hint="Send { taxon_id, original } in the request body.",
                           code=400)

        # Load proteomes from JSON
        proteomes = load_proteomes(JSON_PATH)
        match = next((p for p in proteomes if str(p.get("taxon_id")) == str(taxon_id)), None)

        if not match:
            return respond(False, "No match found for Taxon ID",
                           where="fix_taxid",
                           hint="Verify the taxon_id in the proteomes JSON file.",
                           code=404)

        return respond(True, "Taxon fixed",
                       where="fix_taxid",
                       payload={
                           "found": True,
                           "label": match.get("label"),
                           "has_file": bool(match.get("file_url") and match["file_url"] != "NA"),
                           "file_url": match.get("file_url", "")
                       })

    except Exception as e:
        return respond(False, f"Unexpected error in fix_taxid: {e}",
                       where="fix_taxid",
                       hint="Check the proteomes JSON and the request data.",
                       code=500)

@app.route("/run_go_analysis", methods=["POST"])
def run_go_analysis():
    try:
        excel_path = os.path.join(RESULTS_FOLDER, "Gene_Ontology_Analysis.xlsx")
        PLOTS_FOLDER = os.path.join("static", "plots")
        os.makedirs(PLOTS_FOLDER, exist_ok=True)
        image_path = os.path.join(PLOTS_FOLDER, "annotation_distribution.png")

        if not os.path.exists(excel_path):
            return respond(False, "GOA Excel not found",
                           where="run_go_analysis",
                           hint="Click 'Download GOA files' to generate the Excel first.",
                           code=404)

        try:
            generate_go_image_from_excel(excel_path, image_path)
        except Exception as e:
            return respond(False, f"Failed to generate annotation figure: {e}",
                           where="run_go_analysis",
                           hint="Check the 'Gene_Ontology_Analysis.xlsx' file.",
                           code=500)

        return respond(True, "Annotation distribution successfully generated",
                       where="run_go_analysis",
                       payload={"image_file_path": image_path})

    except Exception as e:
        return respond(False, f"Unexpected error in run_go_analysis: {e}",
                       where="run_go_analysis",
                       hint="Check logs and verify file paths and permissions.",
                       code=500)

@app.route('/foreground_analysis', methods=['POST'])
def foreground_analysis():
    """Stores the foreground (pasted IDs or orthogroup-expanded IDs) in session, with detailed logs."""
    try:
        data = request.get_json(silent=True) or {}
        uniprot_ids = parse_uniprot_block(data.get('uniprot_ids', []))
        use_orthogroups = bool(data.get('use_orthogroups', False))
        print(f"[FG] Received UniProt IDs (n={len(uniprot_ids)}): {uniprot_ids}", flush=True)
        print(f"[FG] Use Orthogroups flag: {use_orthogroups}", flush=True)

        if not uniprot_ids:
            return respond(False, "No UniProt IDs provided",
                           where="foreground_analysis",
                           hint="Paste at least one UniProt ID.",
                           code=400)

        excel_path = os.path.join(RESULTS_FOLDER, "Gene_Ontology_Analysis.xlsx")
        if not os.path.exists(excel_path):
            print(f"[FG][ERR] Gene Ontology Analysis file not found at: {excel_path}", flush=True)
            return respond(False, "Gene Ontology Analysis file not found.",
                           where="foreground_analysis",
                           hint="Click 'Download GOA files' first.",
                           code=404)

        print("[FG] Loading sheets from Excel file ...", flush=True)
        try:
            ortogrupos_iniciales = pd.read_excel(excel_path, sheet_name='Initial Groups')
            ortogrupos_interes   = pd.read_excel(excel_path, sheet_name='Groups of Interest')
        except Exception as e:
            print(f"[FG][ERR] Failed reading sheets: {e}", flush=True)
            return respond(False, f"Malformed Excel file: {e}",
                           where="foreground_analysis",
                           hint="Re-generate the Excel using 'Download GOA files'.",
                           code=500)
        print(f"[FG] Sheets loaded. Initial Groups rows={len(ortogrupos_iniciales)}, Groups of Interest rows={len(ortogrupos_interes)}", flush=True)

        # Expand by orthogroups
        uniprot_set = set(uniprot_ids)
        selected_orthogroups = set()
        protein_set = set()

        if use_orthogroups:
            # Detect orthogroups containing any of the provided IDs
            hits_ogs = 0
            for _, row in ortogrupos_iniciales.iterrows():
                og = row['Orthogroup']
                proteins = row[1:]
                for protein in proteins.dropna():
                    s = str(protein)
                    hits = re.findall(r'\|([^|]+)\|', s)
                    if any(uid in uniprot_set for uid in hits):
                        selected_orthogroups.add(og)
                        hits_ogs += 1
                        break
            print(f"[FG] Orthogroups matched by pasted IDs: {hits_ogs}", flush=True)

            # Expand IDs from 'Groups of Interest'
            exp_added = 0
            for og in selected_orthogroups:
                sub = ortogrupos_interes[ortogrupos_interes['Orthogroup'] == og]
                for _, row in sub.iterrows():
                    proteins = row.dropna().astype(str)
                    for protein in proteins:
                        if protein not in ('Annotation Percentage', 'Porcentaje de Anotación'):
                            ids = re.findall(r'\|([^|]+)\|', protein)
                            protein_set.update(ids)
                            exp_added += len(ids)
            print(f"[FG] Expanded foreground IDs added from orthogroups: {exp_added}", flush=True)

            if not selected_orthogroups:
                print("[FG][WARN] No orthogroups matched the provided UniProt IDs.", flush=True)
        else:
            protein_set.update(uniprot_ids)
            # Report which orthogroups contain any of the IDs (useful info)
            hits_ogs = 0
            for _, row in ortogrupos_iniciales.iterrows():
                og = row['Orthogroup']
                proteins = row[1:]
                for protein in proteins.dropna():
                    s = str(protein)
                    hits = re.findall(r'\|([^|]+)\|', s)
                    if any(uid in uniprot_set for uid in hits):
                        selected_orthogroups.add(og)
                        hits_ogs += 1
                        break
            print(f"[FG] Orthogroups containing at least one pasted ID: {hits_ogs}", flush=True)

        final_protein_list = sorted(protein_set)
        selected_orthogroups_list = sorted(selected_orthogroups)

        # Store in session
        session['foreground_proteins'] = final_protein_list
        session['selected_orthogroups'] = selected_orthogroups_list

        # Clear logs
        print(f"[FG] Selected Orthogroups (n={len(selected_orthogroups_list)}): {selected_orthogroups_list}", flush=True)
        print(f"[FG] Final Protein List size: {len(final_protein_list)}", flush=True)

        return respond(True, "Foreground analysis completed successfully",
                       where="foreground_analysis",
                       payload={"foreground_proteins": final_protein_list})
    except Exception as e:
        print("[FG][ERR] Unexpected error:", str(e), flush=True)
        return respond(False, f"Unexpected error: {e}",
                       where="foreground_analysis",
                       code=500)

@app.route('/background_analysis', methods=['POST'])
def background_analysis():
    """
    Defines the background for GO analysis:
      - choice '4': pasted UniProt IDs (with or without 'use_orthogroups')
      - choice '5': use ALL downloaded GOA files as background
    """
    try:
        data = request.get_json(silent=True) or {}
        choice = str(data.get('background_choice', '')).strip()
        use_orthogroups = bool(data.get('use_orthogroups', False))
        custom_uniprot_ids = parse_uniprot_block(data.get('custom_uniprot_ids', []))

        print(f"[BG] choice={choice} use_orthogroups={use_orthogroups} custom_ids={len(custom_uniprot_ids)}", flush=True)
        if choice == '4' and not custom_uniprot_ids:
            return respond(False, "No UniProt IDs provided",
                           where="background_analysis",
                           hint="Paste at least one UniProt ID for the background.",
                           code=400)

        excel_path = os.path.join(RESULTS_FOLDER, "Gene_Ontology_Analysis.xlsx")
        if not os.path.exists(excel_path):
            print(f"[BG][ERR] Excel not found at: {excel_path}", flush=True)
            return respond(False, "Gene Ontology Analysis file not found.",
                           where="background_analysis",
                           hint="Click 'Download GOA files' first.",
                           code=404)

        try:
            ortogrupos_iniciales = pd.read_excel(excel_path, sheet_name='Initial Groups')
            ortogrupos_interes   = pd.read_excel(excel_path, sheet_name='Groups of Interest')
        except Exception as e:
            print(f"[BG][ERR] Failed reading sheets: {e}", flush=True)
            return respond(False, f"Malformed Excel file: {e}",
                           where="background_analysis",
                           hint="Re-generate the Excel using 'Download GOA files'.",
                           code=500)

        background_ids = set()

        if choice == '4':
            if use_orthogroups:
                # Select orthogroups containing any of the custom IDs
                sel_ogs = set()
                base_set = set(custom_uniprot_ids)
                og_hits = 0
                for _, row in ortogrupos_iniciales.iterrows():
                    og = row['Orthogroup']
                    proteins = row[1:]
                    for protein in proteins.dropna():
                        s = str(protein)
                        hits = re.findall(r'\|([^|]+)\|', s)
                        if any(uid in base_set for uid in hits):
                            sel_ogs.add(og)
                            og_hits += 1
                            break
                print(f"[BG] Orthogroups matched by custom IDs: {og_hits}", flush=True)
                # Expand IDs from 'Groups of Interest'
                exp_added = 0
                for og in sel_ogs:
                    sub = ortogrupos_interes[ortogrupos_interes['Orthogroup'] == og]
                    for _, row in sub.iterrows():
                        proteins = row.dropna().astype(str)
                        for protein in proteins:
                            if protein not in ('Annotation Percentage', 'Porcentaje de Anotación'):
                                ids = re.findall(r'\|([^|]+)\|', protein)
                                background_ids.update(ids)
                                exp_added += len(ids)
                print(f"[BG] Expanded background IDs added from orthogroups: {exp_added}", flush=True)
            else:
                background_ids.update(custom_uniprot_ids)
                print(f"[BG] Background from pasted IDs only: n={len(background_ids)}", flush=True)

        elif choice == '5':
            # Use all downloaded GOA files -> universe will be built later in /gene_ontology_analysis
            if not os.path.isdir(GOA_DOWNLOAD_FOLDER):
                print(f"[BG][ERR] GOA folder not found: {GOA_DOWNLOAD_FOLDER}", flush=True)
                return respond(False, "GOA download folder not found",
                               where="background_analysis",
                               hint="Download the GOA files from the species table first.",
                               code=400)

            goa_files = [f for f in os.listdir(GOA_DOWNLOAD_FOLDER)
                         if f.endswith((".gaf", ".gaf.gz", ".goa", ".goa.gz"))]
            print(f"[BG] GOA files found: {len(goa_files)}", flush=True)
            if not goa_files:
                return respond(False, "No GOA files found",
                               where="background_analysis",
                               hint="Click 'Download GOA files' before using this option.",
                               code=400)

            session["background_mode"] = "goa_all"
            session["background_goa_files"] = goa_files
            # background_ids left empty; will be calculated later in /gene_ontology_analysis
            session["background_ids"] = session.get("background_ids", [])
            print(f"[BG] ✅ Set to ALL GOA files ({len(goa_files)})", flush=True)
            return respond(True, "Background set to all GOA files",
                           where="background_analysis",
                           payload={"background_files": goa_files,
                                    "background_ids": session.get("background_ids", [])})

        else:
            return respond(False, f"Background choice '{choice}' not implemented",
                           where="background_analysis",
                           hint="Use option 4 (pasted IDs) or 5 (use GOA).",
                           code=400)

        # Save to session (option 4)
        session["background_mode"] = "ids"
        session["background_ids"] = sorted(background_ids)
        print(f"[BG] ✅ Selected background IDs: {len(background_ids)}", flush=True)
        return respond(True, "Background successfully stored",
                       where="background_analysis",
                       payload={"background_ids": sorted(background_ids)})
    except Exception as e:
        print(f"[BG][ERR] Unexpected error: {e}", flush=True)
        return respond(False, str(e), where="background_analysis", code=500)

@app.route('/gene_ontology_analysis', methods=['POST'])
def gene_ontology_analysis():
    try:
        # -------------------------------
        # FRONTEND PARAMETERS
        # -------------------------------
        data = request.get_json(silent=True) or {}
        p_value_threshold = float(data.get('p_value', 0.05))
        max_terms = data.get('max_terms')  # None or int
        min_depth = int(data.get('min_depth', 2))
        print("="*80)
        print(f"[GO] ▶ Starting GO Analysis")
        print(f"     - p_value_threshold = {p_value_threshold}")
        print(f"     - min_depth = {min_depth}")
        print(f"     - max_terms = {max_terms}", flush=True)

        # -------------------------------
        # SESSION DATA
        # -------------------------------
        foreground = session.get("foreground_proteins", [])
        background_ids = session.get("background_ids", [])
        bg_mode = session.get("background_mode")  # "goa_all" | "ids"
        goa_mapping = session.get("goa_mapping", {})

        if not foreground:
            print("[GO][ERR] ❌ Foreground missing")
            return respond(False, "Foreground missing",
                           where="gene_ontology_analysis",
                           hint="Load the foreground before running the analysis.",
                           code=400)

        print(f"[GO] Foreground proteins loaded: {len(foreground)}")
        if len(foreground) < 10:
            print(f"[GO] Example foreground IDs: {foreground}")

        # -------------------------------
        # BUILD id2gos FROM GOA FILES
        # -------------------------------
        limit_files = list(set(goa_mapping.values())) if goa_mapping else None
        print(f"[GO] Building id2gos from folder={GOA_DOWNLOAD_FOLDER} limit_files={limit_files}")
        id2gos = build_id2gos_from_goa_folder(GOA_DOWNLOAD_FOLDER, limit_files=limit_files)
        print(f"[GO] id2gos constructed: {len(id2gos)} proteins with GO terms")

        # -------------------------------
        # DEFINE BACKGROUND
        # -------------------------------
        if bg_mode == "goa_all":
            background_ids = sorted(id2gos.keys())
            print(f"[GO] Background mode=ALL, proteins={len(background_ids)}")

        if not background_ids:
            print("[GO][ERR] ❌ Background missing")
            return respond(False, "Background missing",
                           where="gene_ontology_analysis",
                           hint="Define the background before proceeding.",
                           code=400)

        bg_set = set(background_ids)
        assoc_bg = {str(g): set(gos) for g, gos in id2gos.items() if g in bg_set and gos}
        print(f"[GO] assoc_bg built: {len(assoc_bg)} proteins with GO terms")

        # Detect malformed entries
        bad = [(g, type(v)) for g, v in assoc_bg.items() if not isinstance(v, set)]
        if bad:
            print(f"[GO][WARN] Found {len(bad)} non-set entries in assoc_bg. Example: {bad[:5]}")

        # Example association
        if assoc_bg:
            some_gene, some_gos = next(iter(assoc_bg.items()))
            print(f"[GO] Example assoc: {some_gene} -> {list(some_gos)[:5]}")

        # -------------------------------
        # FILTER FOREGROUND
        # -------------------------------
        fg_in_bg = [g for g in foreground if g in assoc_bg]
        print(f"[GO] Foreground overlap: {len(fg_in_bg)} / {len(foreground)} in background")

        if not fg_in_bg:
            print("[GO][ERR] ❌ Foreground has no overlap with background+GO")
            return respond(False, "Foreground IDs have no GO terms in background",
                           where="gene_ontology_analysis",
                           hint="Check that your foreground IDs have GO annotations.",
                           code=400)

        # -------------------------------
        # LOAD ONTOLOGY
        # -------------------------------
        try:
            godag = ensure_godag(GO_ROOT_OBO)
            print(f"[GO] GODag loaded: {len(godag)} terms")
        except Exception as e:
            print(f"[GO][ERR] ❌ GODag load failed: {e}")
            raise

        # -------------------------------
        # ENRICHMENT ANALYSIS
        # -------------------------------
        print("[GO] Running GOEnrichmentStudy ...")
        from goatools.goea.go_enrichment_ns import GOEnrichmentStudy  # ✅ correct for v1.4.12

        try:
            goea = GOEnrichmentStudy(
                list(bg_set),   # universe
                assoc_bg,       # gene -> set(GO)
                godag,
                methods=['fdr_bh'],
                log=None
            )
        except Exception as e:
            print("[GO][CRASH] ❌ Error initializing GOEA")
            print(f"    - assoc_bg type={type(assoc_bg)} size={len(assoc_bg)}")
            sample = [(g, type(v), list(v)[:10]) for g, v in list(assoc_bg.items())[:5]]
            print(f"    - Sample entries: {sample}")
            raise

        results = goea.run_study(fg_in_bg)
        print(f"[GO] Raw results: {len(results)} terms")

        # -------------------------------
        # FILTER SIGNIFICANT RESULTS
        # -------------------------------
        sig = []
        for r in results:
            if r.p_fdr_bh is None or r.p_fdr_bh >= p_value_threshold:
                continue
            depth = godag[r.GO].depth if r.GO in godag else 0
            if depth >= min_depth:
                sig.append(r)

        print(f"[GO] Significant after FDR<{p_value_threshold} & depth≥{min_depth}: {len(sig)}")

        # -------------------------------
        # SPLIT BY NAMESPACE
        # -------------------------------
        def top_by_ns(ns, N=None):
            arr = [r for r in sig if r.goterm.namespace == ns]
            arr = sorted(arr, key=lambda x: (x.p_fdr_bh, x.p_uncorrected))
            return arr[:N] if (N and isinstance(N, int)) else arr

        bp_results = top_by_ns("biological_process", max_terms)
        cc_results = top_by_ns("cellular_component", max_terms)
        mf_results = top_by_ns("molecular_function", max_terms)

        print(f"[GO] Split by namespace: BP={len(bp_results)}, CC={len(cc_results)}, MF={len(mf_results)}")

        # -------------------------------
        # FIGURE
        # -------------------------------
        def prep(res, max_label_length=30):
            labels = [(r.name[:max_label_length] + "…") if len(r.name) > max_label_length else r.name for r in res]
            vals = [(-np.log10(r.p_fdr_bh)) if r.p_fdr_bh and r.p_fdr_bh > 0 else 0 for r in res]
            return labels, vals

        from matplotlib.gridspec import GridSpec
        fig = plt.figure(figsize=(20, 15))
        gs = GridSpec(2, 2, width_ratios=[1, 1], height_ratios=[0.25, 0.75])

        # Biological Process
        ax_bp = fig.add_subplot(gs[:, 0])
        labels, vals = prep(bp_results)
        ax_bp.barh(labels, vals, color="#1f77b4")
        ax_bp.set_title('Biological Process')
        ax_bp.set_xlabel('-log10(FDR)')
        ax_bp.invert_yaxis()

        # Cellular Component
        ax_cc = fig.add_subplot(gs[0, 1])
        labels, vals = prep(cc_results)
        ax_cc.barh(labels, vals, color="#4CB44C")
        ax_cc.set_title('Cellular Component')
        ax_cc.set_xlabel('-log10(FDR)')
        ax_cc.invert_yaxis()

        # Molecular Function
        ax_mf = fig.add_subplot(gs[1, 1])
        labels, vals = prep(mf_results)
        ax_mf.barh(labels, vals, color="#ce4242")
        ax_mf.set_title('Molecular Function')
        ax_mf.set_xlabel('-log10(FDR)')
        ax_mf.invert_yaxis()

        plt.tight_layout()

        # Save figure on server
        figure_path = os.path.join("static", "plots", "go_analysis_figure.png")
        plt.savefig(figure_path)
        plt.close(fig)
        print(f"[GO] 📊 Figure generated: {figure_path}")

        # -------------------------------
        # EXCEL OUTPUT
        # -------------------------------
        out_xlsx = os.path.join(RESULTS_FOLDER, "go_enrichment_report.xlsx")
        with pd.ExcelWriter(out_xlsx) as xw:
            for ns, res in (("BP", bp_results), ("CC", cc_results), ("MF", mf_results)):
                df = pd.DataFrame({
                    "GO": [r.GO for r in res],
                    "name": [r.name for r in res],
                    "NS": [r.goterm.namespace for r in res],
                    "-log10(FDR)": [(-np.log10(r.p_fdr_bh)) for r in res],
                    "study_count": [r.study_count for r in res],
                    "study_n": [r.study_n for r in res],
                    "pop_count": [r.pop_count for r in res],
                    "pop_n": [r.pop_n for r in res],
                }) if res else pd.DataFrame(columns=[
                    "GO","name","NS","-log10(FDR)","study_count","study_n","pop_count","pop_n"
                ])
                df.to_excel(xw, sheet_name=ns, index=False)
        print(f"[GO] 📑 Excel generated: {out_xlsx}")

        # -------------------------------
        # FINAL RESPONSE
        # -------------------------------
        return respond(True, "GO analysis completed successfully",
                       where="gene_ontology_analysis",
                       payload={
                           "bp_results": [{"GO": r.GO, "name": r.name, "p_fdr_bh": r.p_fdr_bh} for r in bp_results],
                           "cc_results": [{"GO": r.GO, "name": r.name, "p_fdr_bh": r.p_fdr_bh} for r in cc_results],
                           "mf_results": [{"GO": r.GO, "name": r.name, "p_fdr_bh": r.p_fdr_bh} for r in mf_results],
                           "image_file_path": figure_path,
                           "excel_file_path": "download_go_enrichment_excel"
                       })

    except Exception as e:
        print(f"[GO][ERR] ❌ Unexpected error in gene_ontology_analysis: {e}")
        import traceback; traceback.print_exc()
        return respond(False, f"Unexpected error: {e}",
                       where="gene_ontology_analysis",
                       hint="Check logs and make sure OBO/GOA files exist.",
                       code=500)

@app.route("/download_go_enrichment_excel")
def download_go_enrichment_excel():
    excel_path = os.path.join(RESULTS_FOLDER, "go_enrichment_report.xlsx")
    if not os.path.exists(excel_path):
        return "Excel file not available", 404
    return send_file(excel_path, as_attachment=True)

@app.route("/go_status")
def go_status():
    try:
        info = {
            "modo": session.get("modo"),
            "ruta_carpeta": session.get("ruta_carpeta"),
            "species_count": len(session.get("species", [])),
            "fg_count": len(session.get("foreground_proteins", [])),
            "bg_count": len(session.get("background_ids", [])),
            "goa_mapping_count": len(session.get("goa_mapping", {})),
            "bg_mode": session.get("background_mode"),
        }
        return respond(True, "GO status", where="go_status", payload=info)
    except Exception as e:
        return respond(False, f"Unexpected error in go_status: {e}",
                       where="go_status", code=500)

@app.route("/generate_go_image", methods=["POST"])
def generate_go_image():
    """
    Uses the Excel generated by /download_goa_files (RESULTS_FOLDER/Gene_Ontology_Analysis.xlsx)
    and creates the 4-in-1 figure in static/plots.
    Returns JSON with 'image_file_path' (only filename) for the frontend to display
    as /static/plots/<name>.
    """
    try:
        # 1) Paths
        excel_path = os.path.join(RESULTS_FOLDER, "Gene_Ontology_Analysis.xlsx")
        if not os.path.exists(excel_path):
            return respond(
                False,
                "Excel not found. Run /download_goa_files first.",
                where="generate_go_image",
                hint="Make sure the GOA files were downloaded and the Excel file was generated.",
                code=404
            )

        # 2) Ensure plots directory
        crear_directorio_plots()  # already defined in your app

        # 3) Output (stable name for frontend)
        image_filename = "go_annotation_distribution.png"
        image_output_path = os.path.join("static", "plots", image_filename)

        # 4) Generate image
        generate_go_image_from_excel(excel_path, image_output_path)

        # Quick verification
        if not os.path.exists(image_output_path):
            return respond(
                False,
                "Image could not be generated.",
                where="generate_go_image",
                hint="Check that the Excel file contains 'Initial Groups' and 'Annotation Percentage' columns.",
                code=500
            )

        # 5) Response for frontend
        return respond(
            True,
            "GO image successfully generated",
            where="generate_go_image",
            payload={"image_file_path": image_filename}
        )

    except Exception as e:
        return respond(
            False,
            f"Unexpected error: {e}",
            where="generate_go_image",
            code=500
        )


if __name__ == "__main__":
    port = find_free_port()
    print(f"🚀 Starting Flask on port {port}")
    threading.Timer(1.25, open_browser, args=(port,)).start()
    app.run(debug=True, use_reloader=False, port=port)