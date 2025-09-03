import pandas as pd
from pathlib import Path
from typing import List, Dict
from langchain.schema import Document


# 🔍 Mots-clés pour détection
KEYWORDS_BESOIN =  ["besoin", "besoins", "exigence", "exigences", "requirement", "requirements",
            "fonction", "fonctions", "question", "questions", "demande", "demandes",
            "specification", "specifications"
        ]
KEYWORDS_REPONSE = [
            "response", "responses", "answer", "answers", "commentaire", "commentaires",
            "comment", "feedback", "details", "réponse", "réponses", "solution", "solutions"
        ]

def detect_columns(all_sheets: Dict[str, pd.DataFrame], filename: str) -> List[Dict]:
    """
    Détecte automatiquement les colonnes "besoin" et "réponses" dans un fichier Excel.
    """
    onglets_traites = []

 # Analyser chaque onglet
    for sheet_name, df in all_sheets.items():
        print(f"\n🔍 TRAITEMENT ONGLET: '{sheet_name}'")
        print(f"   Dimensions: {df.shape}")


        # Chercher dans les 20 premières lignes de cet onglet
        for row_idx in range(min(20, len(df))):
            row = df.iloc[row_idx]
            print(f"🔍 Analyse ligne {row_idx} → {row.tolist()}") ######### RAJOUTE POUR TEST ################

            # Chercher un mot-clé BESOIN
            besoin_col = None
            besoin_content = None
            besoin_keyword = None

            for col_idx, cell_value in enumerate(row):
                if pd.notna(cell_value):
                    cell_str = str(cell_value).lower()

                    # Chercher dans les mots-clés BESOIN                   
                    for keyword in KEYWORDS_BESOIN:
                        if keyword in cell_str:
                            print(f"   ✅ BESOIN trouvé: '{cell_value}' → '{keyword}' (ligne {row_idx}, col {col_idx})") #### POUR VERIFICATION ###
                            besoin_col = col_idx
                            besoin_content = cell_value
                            besoin_keyword = keyword
                            break
                if besoin_col is not None:
                    break

            # Si BESOIN trouvé, chercher RÉPONSE(S) sur la même ligne
            if besoin_col is not None:
                reponses_trouvees = []

                for col_idx, cell_value in enumerate(row):
                    if col_idx != besoin_col and pd.notna(cell_value):
                        cell_str = str(cell_value).lower()

                    # Chercher dans les mots-clés RÉPONSE    
                        for keyword in KEYWORDS_REPONSE:
                            if keyword in cell_str:
                                print(f"      💬 RÉPONSE trouvée: '{cell_value}' → '{keyword}' (col {col_idx})") #### POUR VERIFICATION ###
                                reponses_trouvees.append({
                                    'col': col_idx,
                                    'content': cell_value,
                                    'keyword': keyword
                                })
                                break
                
                 # AJOUTER CET ONGLET À LA LISTE TRAITÉE
                if len(reponses_trouvees) > 0:
                    #print(f"\n✅ ONGLET '{sheet_name}' TRAITÉ !")
                    #print(f"   📋 BESOIN: Ligne {row_idx}, Colonne {besoin_col}")
                    #print(f"   💬 RÉPONSES: {len(reponses_trouvees)} trouvée(s)")

                    onglets_traites.append({
                        'onglet': sheet_name,
                        'ligne_detection': row_idx,
                        'besoin': {
                            'colonne': besoin_col,
                            'contenu': besoin_content,
                            'mot_cle': besoin_keyword
                        },
                        'reponses': reponses_trouvees,
                        'df': df,
                        'exploitable': True
                    })
                    break

    return onglets_traites


def create_smart_chunks_from_detected(onglet_data: Dict, filename: str) -> List[Document]:
    """
    Crée des chunks intelligents à partir d’un onglet détecté.
    """
    documents = []
    df = onglet_data['df']
    sheet_name = onglet_data['onglet']
    header_row_idx = onglet_data['ligne_detection']
    besoin_col = onglet_data['besoin']['colonne']
    reponses_cols = [r['col'] for r in onglet_data['reponses']]
    data_start_row = header_row_idx + 1
    data_rows = df.iloc[data_start_row:]

    
    for data_idx, (_, row) in enumerate(data_rows.iterrows()):
        actual_row_num = data_start_row + data_idx + 1
        besoin_content = str(row.iloc[besoin_col]).strip() if pd.notna(row.iloc[besoin_col]) else ""

        reponses_parts = []
        for resp_col in reponses_cols:
            if resp_col < len(row):
                resp_content = str(row.iloc[resp_col]).strip() if pd.notna(row.iloc[resp_col]) else ""
                if resp_content and resp_content.lower() not in ['nan', '', '0']:
                    reponses_parts.append(resp_content)

        reponses_content = " - ".join(reponses_parts) if reponses_parts else ""

        if (not besoin_content or besoin_content.lower() in ['nan', ''] or len(besoin_content) < 10 or not reponses_content):
            continue

        metadata_dict = {}
        for col_idx in range(len(row)):
            if col_idx not in [besoin_col] + reponses_cols:
                meta_value = row.iloc[col_idx]
                if pd.notna(meta_value) and str(meta_value).strip().lower() not in ['nan', '']:
                    metadata_dict[f'meta_col_{col_idx}'] = str(meta_value).strip()

        content_parts = [
            f"=== CONTEXTE ===",
            f"Fichier: {Path(filename).stem}",
            f"Section/Onglet: {sheet_name}",
            f"Lignes: {actual_row_num}",
            f"Type: Tableau de besoins/spécifications eQMS",
            "",
            f"=== CONTENU MÉTIER ===",
            f"--- BESOIN CLIENT ---",
            f"Catégorie: {onglet_data['besoin']['contenu']}",
            f"Contenu: {besoin_content}",
            "",
            f"--- RÉPONSES FOURNISSEUR ---",
            f"Sources: {', '.join([r['content'] for r in onglet_data['reponses']])}",
            f"Contenu: {reponses_content}",
        ]

        if metadata_dict:
            content_parts.append("")
            content_parts.append("--- MÉTADONNÉES ---")
            for key, value in metadata_dict.items():
                content_parts.append(f"{key}: {value}")

        content = "\n".join(content_parts)

        doc_metadata = {
            "source": filename,
            "sheet_name": sheet_name,
            "chunk_id": f"{Path(filename).stem}_{sheet_name}_L{actual_row_num}",
            "start_row": actual_row_num,
            "end_row": actual_row_num,
            "has_content": True,
            "chunk_type": "smart_business",
            **metadata_dict
        }

        documents.append(Document(page_content=content, metadata=doc_metadata))

    return documents
