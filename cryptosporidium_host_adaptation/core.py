"""Helper Functions for the analysis"""

# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_core.ipynb.

# %% auto 0
__all__ = ['count_variants', 'filter_variants', 'read_vcf', 'find_index', 'expand_multiallelic_variants', 'compute_frequencies',
           'extract_first_ann', 'add_ann_info_to_df', 'mod_hist_legend', 'clean_axes', 'make_circos_plot',
           'kmeans_cluster_analysis', 'elbow_point']

# %% ../nbs/00_core.ipynb 4
import subprocess
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib

from pycirclize import Circos
from pycirclize.parser import Gff
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

# %% ../nbs/00_core.ipynb 5
def count_variants(vcf_file):
    """Count the number of variants in a VCF file using subprocess."""
    if vcf_file.endswith('.gz'):
        cmd = f"bcftools view -H {vcf_file} | wc -l"
    else:
        cmd = f"grep -v '^#' {vcf_file} | wc -l"
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return int(result.stdout.strip())

def filter_variants():
    # Define input and output VCF files
    INPUT_VCF = "../data/freebayes.annotated_pc1.vcf.gz"
    QUAL_FILTERED_VCF = "../data/filtered_qual.vcf"
    DP_FILTERED_VCF = "../data/filtered_dp.vcf"
    SNP_FILTERED_VCF = "../data/filtered_snp.vcf"
    FINAL_VCF = "../data/filtered_final.vcf"
    
    print("======================================")
    print("Starting Variant Filtering Process")
    print("======================================")
    
    # Count initial number of variants
    START_COUNT = count_variants(INPUT_VCF)
    print(f"Total variants before filtering: {START_COUNT}")
    
    # Step 1: Filter out low-quality variants (QUAL < 30)
    subprocess.run(f"bcftools filter -e 'QUAL < 30' {INPUT_VCF} -o {QUAL_FILTERED_VCF}", shell=True)
    QUAL_FILTERED_COUNT = count_variants(QUAL_FILTERED_VCF)
    print(f"Stage 1: QUAL filtering: {START_COUNT - QUAL_FILTERED_COUNT} Variants removed and {QUAL_FILTERED_COUNT} variants left")

    # Step 2: Filter variants based on per-sample depth (FORMAT/DP < 10 or > 150)
    subprocess.run(f"bcftools view -i 'FMT/DP >= 30 & FMT/DP <= 150' {QUAL_FILTERED_VCF} -o {DP_FILTERED_VCF}", shell=True)
    DP_FILTERED_COUNT = count_variants(DP_FILTERED_VCF)
    print(f"Stage 2: FORMAT/DP filtering, DP >= 30 & DP <= 150: {QUAL_FILTERED_COUNT - DP_FILTERED_COUNT} Variants removed and {DP_FILTERED_COUNT} variants left")

    # Step 3: Retain SNPs and indels (Remove other variant types if any)
    subprocess.run(f"bcftools view -v snps,indels {DP_FILTERED_VCF} -o {SNP_FILTERED_VCF}", shell=True)
    SNP_FILTERED_COUNT = count_variants(SNP_FILTERED_VCF)
    print(f"Stage 3: After keeping SNPs and indels: {DP_FILTERED_COUNT - SNP_FILTERED_COUNT} Variants removed and {SNP_FILTERED_COUNT} variants left")

    # Rename final output
    os.rename(SNP_FILTERED_VCF, FINAL_VCF)
    FINAL_COUNT = count_variants(FINAL_VCF)


# %% ../nbs/00_core.ipynb 7
def read_vcf(vcf_file):
    """Reads a VCF file, automatically detecting the header and using correct column names."""
    
    # Find the header line dynamically
    with open(vcf_file, "r") as f:
        for line in f:
            if line.startswith("#CHROM"):
                header = line.strip().split("\t")  # Extract column names
                break  # Stop searching after finding header
    
    # Read VCF using Pandas, skipping comment lines
    df = pd.read_csv(vcf_file, sep="\t", comment="#", header=None, names=header)
    return df


# %% ../nbs/00_core.ipynb 9
def find_index(format_value, field):
    """Finds the index of a specific field (e.g., RO, AO, DP) in the FORMAT column."""
    item_list = format_value.split(':')
    return item_list.index(field) if field in item_list else None

def expand_multiallelic_variants(df_vcf):
    """
    Extracts allele counts (RO, AO, DP) for each sample from the VCF DataFrame
    and expands multi-allelic variants into separate rows.
    """

    # Extract sample names (everything after FORMAT column)
    sample_names = df_vcf.columns[9:]  # Skip CHROM, POS, ID, REF, ALT, QUAL, FILTER, INFO, FORMAT

    # Find the index positions of RO, AO, and DP in the FORMAT field
    format_example = df_vcf['FORMAT'].values[0]  # Take the first row as an example
    ro_index = find_index(format_example, 'RO')
    ao_index = find_index(format_example, 'AO')
    dp_index = find_index(format_example, 'DP')

    # Ensure indices exist
    if None in [ro_index, ao_index, dp_index]:
        raise ValueError("RO, AO, or DP field not found in FORMAT column.")

    # Initialize an empty list to store expanded rows
    expanded_rows = []

    for _, row in df_vcf.iterrows():
        # Split ALT alleles (multi-allelic sites will have multiple ALT values)
        alt_alleles = row['ALT'].split(',')
        info_type = row['INFO'].split('TYPE=')[1].split(';')[0].split(',')
        
        # Process each ALT allele separately
        for i, (alt, inty )in enumerate(zip(alt_alleles,info_type)):
            new_row = {
                "#CHROM": row["#CHROM"],
                "POS": row["POS"],
                "REF": row["REF"],
                "ALT": alt,  # Assign each alternate allele to a separate row
                "INFO_TYPE": inty
            }

            for sample in sample_names:
                # Split FORMAT fields for the sample
                sample_values = row[sample].split(':')
                
                # Extract and store RO and DP
                new_row[f"RO_{sample}"] = int(sample_values[ro_index]) if sample_values[ro_index] != '.' else 0
                new_row[f"DP_{sample}"] = int(sample_values[dp_index]) if sample_values[dp_index] != '.' else 0

                # Extract AO for the specific ALT allele
                ao_values = sample_values[ao_index].split(',')  # Multiple values for multiple ALT alleles
                new_row[f"AO_{sample}"] = int(ao_values[i]) if i < len(ao_values) and ao_values[i] != '.' else 0

            # Append expanded row
            expanded_rows.append(new_row)

    # Convert list of dictionaries into DataFrame
    expanded_df = pd.DataFrame(expanded_rows)

    return expanded_df

# %% ../nbs/00_core.ipynb 10
def compute_frequencies(df_counts):
    """
    Computes allele frequency (AF = AO / DP) for each sample in the dataset.
    """

    # Extract sample names from AO columns
    sample_names = [col.replace("AO_", "") for col in df_counts.columns if col.startswith("AO_")]

    # Create a new DataFrame to store allele frequencies
    df_af = df_counts[['#CHROM', 'POS', 'REF', 'ALT']].copy()

    for sample in sample_names:
        ao_col = f"AO_{sample}"
        dp_col = f"DP_{sample}"
        af_col = f"AF_{sample}"
        df_af[af_col] = df_counts[ao_col] / df_counts[dp_col] #(df_counts[ro_col] + df_counts[ao_col])

    return df_af


# %% ../nbs/00_core.ipynb 11
def extract_first_ann(info_field):
    """
    Extract the first ANN annotation from a VCF INFO field.
    
    Parameters:
    -----------
    info_field : str
        The INFO field from a VCF file
    
    Returns:
    --------
    dict
        A dictionary containing the variant type, impact, and gene ID,
        or None if no ANN field is found
    """
    # Check if there's an ANN field
    if 'ANN=' not in info_field:
        return None
    
    # Extract the ANN part
    ann_start = info_field.find('ANN=')
    # Take everything after "ANN="
    ann_content = info_field[ann_start + 4:]
    
    # If there are other fields after ANN, cut them off
    if ';' in ann_content:
        ann_content = ann_content.split(';')[0]
    
    # Split by comma to get individual annotations
    annotations = ann_content.split(',')
    
    # Get the first annotation
    first_ann = annotations[0]
    
    # Split by pipe (|) to get annotation fields
    ann_fields = first_ann.split('|')
    
    # Create result dictionary
    # Standard VCF ANN format: Allele | Annotation | Impact | Gene_Name | ...
    if len(ann_fields) >= 4:
        result = {
            'allele': ann_fields[0],
            'type': ann_fields[1],
            'impact': ann_fields[2],
            'gene_id': ann_fields[3]
        }
        return result
    else:
        return None



def add_ann_info_to_df(df, info_column='INFO'):
    """
    Extract the first ANN annotation from the INFO field and add as separate columns to a DataFrame.
    
    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame containing VCF data with an INFO column
    info_column : str, default='INFO'
        Name of the column containing the INFO field
        
    Returns:
    --------
    pandas.DataFrame
        The original DataFrame with additional columns for variant type, impact, and gene ID
    """
    # Create new columns with None values
    df['variant_type'] = None
    df['impact'] = None
    df['gene_id'] = None
    df['allele'] = None
    
    # Process each row
    for idx, row in df.iterrows():
        info = row[info_column]
        ann_data = extract_first_ann(info)
        
        if ann_data:
            df.loc[idx, 'variant_type'] = ann_data['type']
            df.loc[idx, 'impact'] = ann_data['impact']
            df.loc[idx, 'gene_id'] = ann_data['gene_id']
            df.loc[idx, 'allele'] = ann_data['allele']
    
    return df

# Example usage
# Assuming you have a DataFrame 'vcf_df' with a column 'INFO' containing VCF INFO fields
# vcf_df = add_ann_info_to_df(vcf_df)

# %% ../nbs/00_core.ipynb 14
def mod_hist_legend(ax, title=False):
    """
    Creates a cleaner legend for histogram plots by using line elements instead of patches.
    
    Motivation:
    - Default histogram legends show rectangle patches which can be visually distracting
    - This function creates a more elegant legend with simple lines matching histogram edge colors
    - Positions the legend outside the plot to avoid overlapping with data
    
    Parameters:
    -----------
    ax : matplotlib.axes.Axes
        The axes object containing the histogram(s)
    title : str or bool, default=False
        Optional title for the legend. If False, no title is displayed
        
    Returns:
    --------
    None - modifies the axes object in place
    """
    # Extract the current handles and labels from the plot
    handles, labels = ax.get_legend_handles_labels()
    
    # Create new line handles that match the edge colors of histogram bars
    # This produces a cleaner, more minimal legend appearance
    new_handles = [matplotlib.lines.Line2D([], [], c=h.get_edgecolor()) for h in handles]
    
    # Create the legend with custom positioning
    # - Places legend outside the plot (to the right) to avoid obscuring the data
    # - Centers the legend vertically for better visual balance
    ax.legend(handles=new_handles, 
              labels=labels, 
              title=title,
              loc='center left', 
              bbox_to_anchor=(1, 0.5))


def clean_axes(ax, offset=10):
    """
    Customizes a matplotlib axes by removing top and right spines,
    and creating a broken axis effect where x and y axes don't touch.
    
    Parameters:
    -----------
    ax : matplotlib.axes.Axes
        The axes object to customize
    offset : int, default=10
        The amount of offset/gap between the x and y axes in points
        
    Returns:
    --------
    ax : matplotlib.axes.Axes
        The same axes object, modified in place
    """
    # Remove the top and right spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    # Make the remaining spines gray for a more subtle look
    ax.spines['left'].set_color('gray')
    ax.spines['bottom'].set_color('gray')
    
    # Create the broken axis effect
    # Move the bottom spine up by offset points
    #ax.spines['bottom'].set_position(('outward', offset))
    
    # Move the left spine right by offset points
    ax.spines['left'].set_position(('outward', offset))
    
    # Return the modified axes
    return ax

# %% ../nbs/00_core.ipynb 16
def make_circos_plot(data):
    
    seqid2size = {
        'CM000429': 875659,
        'CM000430': 985969,
        'CM000431': 1099352,
        'CM000432': 1104417,
        'CM000433': 1080900,
        'CM000434': 1332857,
        'CM000435': 1278458,
        'CM000436': 1344712
    }

    color_dict = {'M': 'green', 'C': 'blue'}

    circos = Circos(seqid2size, space=3, start=-83, end=265, endspace=False)
    circos.text("C. parvum IowaII", r=5, size=18, font={'style': 'italic'})
    
    m_samples = ['AF_M7', 'AF_M5', 'AF_M6', 'AF_M4']
    c_samples = ['AF_C3', 'AF_C2', 'AF_C1']
    
    for sector in circos.sectors:
        sector.text(sector.name[-3:])
        
        m_track = sector.add_track((80, 100))
        m_track.xticks_by_interval(200000, show_label=False)
        m_track.axis()
    
        
        c_track = sector.add_track((55, 75))
        c_track.xticks_by_interval(200000, show_label=False)
        c_track.axis()
        
        # Plot scatter points for each sample group
        for sample in m_samples:
            color = color_dict[sample[3]]
            subset = data[(data['#CHROM'] == sector.name) & (data[sample] > 0)]
            m_track.scatter(
                x=subset['POS'].values,
                y=subset[sample].values,
                c=color,
                s=3,
                vmin=0,
                vmax=1,
                alpha=0.3,
            )
        
        
        for sample in c_samples:
            color = color_dict[sample[3]]
            subset = data[(data['#CHROM'] == sector.name) & (data[sample] > 0)]
            c_track.scatter(
                x=subset['POS'].values,
                y=subset[sample].values,
                c=color,
                s=3,
                vmin=0,
                vmax=1,
                alpha=0.3,
            )

        
        # Optional: Add labels 
        if sector.name == 'CM000429':
            m_track.yticks([0, 1], ["0", "1"], side="left")
            c_track.yticks([0, 1], ["0", "1"], side="left")

            
            circos.text("Cow", r=c_track.r_center, deg=-90, color="blue")
            circos.text("Mouse", r=m_track.r_center, deg=-90, color="green")
    
    circos.plotfig()
    circos.savefig('../data/Circos.svg')
    circos.savefig('../data/Circos.png')

# %% ../nbs/00_core.ipynb 18
def kmeans_cluster_analysis(df, cluster_sizes, random_state=42, features=None, figsize=(12, 6), 
                          standardize=False, fill_na=False):
    """
    Perform K-means clustering analysis on a pandas DataFrame and visualize the results
    with both normalized inertia and silhouette scores on the same plot.
    
    Parameters
    ----------
    df : pandas.DataFrame
        The input data to cluster.
    cluster_sizes : list
        List of cluster sizes (k values) to evaluate.
    random_state : int, optional
        Random seed for reproducibility (default: 42).
    features : list, optional
        List of column names to use for clustering. If None, all columns are used.
    figsize : tuple, optional
        Figure size for the output plot (default: (12, 6)).
    standardize : bool, optional
        Whether to standardize the features (default: False).
    fill_na : bool, optional
        Whether to fill missing values with column means (default: False).
        
    Returns
    -------
    tuple
        (figure, inertia_values, silhouette_values) - The matplotlib figure object,
        the list of inertia values, and the list of silhouette scores.
    """
    # Prepare the data
    if features is None:
        features = df.columns.tolist()
    
    X = df[features].copy()
    
    # Check for non-numeric data
    non_numeric_cols = X.select_dtypes(exclude=['number']).columns.tolist()
    if non_numeric_cols:
        raise ValueError(f"Non-numeric columns found: {non_numeric_cols}. "
                         f"Please remove or transform them before clustering.")
    
    # Handle missing values
    if X.isna().any().any():
        if fill_na:
            print("Filling missing values with column means.")
            X = X.fillna(X.mean())
        else:
            raise ValueError("Missing values found in the data. Set fill_na=True to automatically handle them or preprocess your data before clustering.")
    
    # Prepare data for clustering
    if standardize:
        print("Standardizing features.")
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
    else:
        X_scaled = X.values
    
    # Compute K-means for different cluster sizes
    inertia_values = []
    silhouette_values = []
    
    for k in cluster_sizes:
        # Fit K-means
        kmeans = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        kmeans.fit(X_scaled)
        inertia_values.append(kmeans.inertia_)
        
        # Compute silhouette score (not defined for k=1)
        if k > 1:
            labels = kmeans.labels_
            silhouette_avg = silhouette_score(X_scaled, labels)
            silhouette_values.append(silhouette_avg)
        else:
            silhouette_values.append(0)  # Placeholder for k=1
    
    # Normalize values
    max_inertia = max(inertia_values)
    normalized_inertia = [i / max_inertia for i in inertia_values]
    
    max_silhouette = max(silhouette_values)
    normalized_silhouette = [s / max_silhouette for s in silhouette_values]
    
    # Create the plot
    fig, ax = plt.subplots(figsize=figsize)
    
    # Plot normalized inertia (elbow curve)
    inertia_line, = ax.plot(cluster_sizes, normalized_inertia, 'o-', color='blue', label='Normalized Inertia')
    
    # Plot normalized silhouette scores
    silhouette_line, = ax.plot(cluster_sizes, normalized_silhouette, 'o-', color='red', label='Normalized Silhouette Score')
    
    # Add vertical lines at each cluster size
    for k in cluster_sizes:
        ax.axvline(x=k, color='gray', linestyle='--', alpha=0.3)
    
    # Customize the plot
    ax.set_title('K-means Evaluation', fontsize=15)
    ax.set_xlabel('Number of Clusters (k)', fontsize=12)
    ax.set_ylabel('Normalized Score', fontsize=12)
    ax.set_xticks(cluster_sizes)
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # Find optimal k values
    best_inertia_idx = elbow_point(normalized_inertia)
    best_silhouette_idx = np.argmax(normalized_silhouette)
    
    best_k_inertia = cluster_sizes[best_inertia_idx]
    best_k_silhouette = cluster_sizes[best_silhouette_idx]
    
    # Add arrows to optimal points without text
    inertia_arrow = ax.annotate('', 
                xy=(best_k_inertia, normalized_inertia[best_inertia_idx]),
                xytext=(best_k_inertia+0.5, normalized_inertia[best_inertia_idx]+0.1),
                arrowprops=dict(facecolor='blue', shrink=0.05, width=1.5, headwidth=8))
    
    silhouette_arrow = ax.annotate('', 
                xy=(best_k_silhouette, normalized_silhouette[best_silhouette_idx]),
                xytext=(best_k_silhouette+0.5, normalized_silhouette[best_silhouette_idx]-0.1),
                arrowprops=dict(facecolor='red', shrink=0.05, width=1.5, headwidth=8))
    
    # Create custom legend handles for the arrows
    from matplotlib.lines import Line2D
    
    elbow_arrow_handle = Line2D([0], [0], color='blue', marker='>',
                              markersize=10, linestyle='-', linewidth=0)
    silhouette_arrow_handle = Line2D([0], [0], color='red', marker='>',
                                   markersize=10, linestyle='-', linewidth=0)
    
    # Create a legend with the arrows and lines
    legend_elements = [
        inertia_line, silhouette_line,
        elbow_arrow_handle, silhouette_arrow_handle
    ]
    legend_labels = [
        'Normalized Inertia', 'Normalized Silhouette Score',
        f'Best Elbow (k={best_k_inertia})', f'Best Silhouette (k={best_k_silhouette})'
    ]
    
    # Place the legend outside the plot
    ax.legend(legend_elements, legend_labels, loc='center left', bbox_to_anchor=(1.05, 0.5))
    
    # Adjust layout to make room for the legend
    fig.tight_layout()
    plt.subplots_adjust(right=0.75)
    
    # Return the figure, axis, and values to allow further customization
    return fig, ax, inertia_values, silhouette_values

def elbow_point(values):
    """
    Find the elbow point in a curve using the maximum curvature method.
    
    Parameters
    ----------
    values : list
        The y-values of the curve.
        
    Returns
    -------
    int
        The index of the elbow point.
    """
    # Simple method - find point of maximum curvature
    # Convert to numpy array
    y = np.array(values)
    x = np.arange(len(y))
    
    # Compute first and second derivatives
    dy = np.gradient(y)
    d2y = np.gradient(dy)
    
    # Compute curvature
    curvature = np.abs(d2y) / (1 + dy**2)**1.5
    
    # Return the point of maximum curvature (ignoring the first and last points)
    if len(curvature) <= 2:
        return 0
    return np.argmax(curvature[1:-1]) + 1
