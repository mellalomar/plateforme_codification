import streamlit as st
import pandas as pd
import numpy as np
import re
from io import BytesIO
import os

st.set_page_config(page_title="Plateforme de Codification", layout="wide")

st.title(" Plateforme de Codification des Courses")
st.markdown("Uploadez votre fichier **Programme des courses** et obtenez la codification automatique")
st.markdown("*(Optionnel: Ajoutez le fichier d'engagements et partants pour enrichir l'analyse)*")

# ============================================================================
# FONCTIONS DE CODIFICATION
# ============================================================================

def normaliser_categories(df):
    """Normalise les catégories homologuées"""
    df.loc[df['Catégorie'] == 'EH', 'Catégorie'] = 'E'
    df.loc[df['Catégorie'] == 'DH', 'Catégorie'] = 'D'
    df.loc[df['Catégorie'] == 'CH', 'Catégorie'] = 'C'
    return df

def nettoyer_donnees(df):
    """Nettoie et valide les données pour éviter les erreurs de type"""
    df = df.copy()
    
    # Colonnes critiques
    colonnes_critiques = ['Catégorie', 'Age', 'Origine', 'Race', 'Sous catégorie', 'Remarque']
    
    for col in colonnes_critiques:
        if col in df.columns:
            # Remplacer NaN par des valeurs par défaut
            if col == 'Catégorie':
                df[col] = df[col].fillna('X')
            elif col == 'Age':
                df[col] = df[col].fillna(0)
            elif col == 'Origine':
                df[col] = df[col].fillna(0)
            elif col == 'Race':
                df[col] = df[col].fillna('X')
            elif col in ['Sous catégorie', 'Remarque']:
                df[col] = df[col].fillna('')
            
            # Convertir en string et trimmer les espaces
            df[col] = df[col].astype(str).str.strip()
    
    return df

def creer_id_base(df):
    """Crée l'ID de base: Catégorie + Age + Origine + Race"""
    # S'assurer que les colonnes existent et sont nettoyées
    df['ID_CONDITION'] = (
        df['Catégorie'].astype(str).str.strip() + 
        df['Age'].astype(str).str.strip() + 
        df['Origine'].astype(str).str.strip() + 
        df['Race'].astype(str).str.strip()
    )
    return df

def ajouter_suffixe_jamais_gagne(row):
    """N'ayant jamais gagné/c/a => 0GC | 0GA"""
    texte = str(row['Sous catégorie']).lower().replace("'", "'")
    match = re.search(r"n.?ayant\s+(?:jamais\s+)?gagn[ée]\s*/\s*(carrière|annee|année)", texte, flags=re.IGNORECASE)
    
    if match:
        type_course = match.group(1)
        if "carri" in type_course:
            suffixe = "0GC"
        elif "ann" in type_course:
            suffixe = "0GA"
        else:
            suffixe = ""
        return row['ID_CONDITION'] + suffixe
    return row['ID_CONDITION']

def ajouter_suffixe_x_courses(row):
    """N'ayant pas gagné X course/c/a => XGC | XGA"""
    texte = str(row['Sous catégorie']).lower().replace("'", "'")
    match = re.search(r"n.?ayant\s+pas\s+gagn[ée]\s+(\d+)\s+courses?\s*/\s*(carrière|annee|année)", texte, flags=re.IGNORECASE)
    
    if match:
        nombre = match.group(1)
        type_course = match.group(2)
        if "carri" in type_course:
            suffixe = f"{nombre}GC"
        elif "ann" in type_course:
            suffixe = f"{nombre}GA"
        else:
            suffixe = ""
        return row['ID_CONDITION'] + suffixe
    return row['ID_CONDITION']

def ajouter_handicap(row):
    """Handicap x => Hx (si Sous catégorie est NaN)"""
    if pd.isna(row['Sous catégorie']):
        match = re.search(r"handicap\s*(\d+)", str(row['Remarque']), flags=re.IGNORECASE)
        if match:
            return row['ID_CONDITION'] + f"H{match.group(1)}"
    return row['ID_CONDITION']

def ajouter_suffixe_recu(row):
    """N'ayant pas reçu X.000 DHS/c/a => RXKC | RXKA"""
    texte = str(row['Sous catégorie']).lower().replace("'", "'")
    match = re.search(
        r"n.?ayant\s+pas\s+re[çc]u\s+(\d+)\.000\s+dh\s*/\s*(carrière|annee|année)",
        texte,
        flags=re.IGNORECASE
    )
    
    if match:
        montant = match.group(1)
        type_periode = match.group(2)
        if "carri" in type_periode:
            suffixe = f"R{montant}KC"
        elif "ann" in type_periode:
            suffixe = f"R{montant}KA"
        else:
            suffixe = ""
        return row['ID_CONDITION'] + suffixe
    return row['ID_CONDITION']

def ajouter_suffixe_gagne(row):
    """N'ayant pas gagné X.000 DHS/c/a => GXKC | GXKA"""
    texte = str(row['Sous catégorie']).lower().replace("'", "'")
    match = re.search(
        r"n.?ayant\s+pas\s+gagn[ée]\s+(\d+)\.000\s+dh\s*/\s*(carrière|annee|année)",
        texte,
        flags=re.IGNORECASE
    )
    
    if match:
        montant = match.group(1)
        type_periode = match.group(2)
        if "carri" in type_periode:
            suffixe = f"G{montant}KC"
        elif "ann" in type_periode:
            suffixe = f"G{montant}KA"
        else:
            suffixe = ""
        return row['ID_CONDITION'] + suffixe
    return row['ID_CONDITION']

def ajouter_surcharge(row):
    """Surcharge/c/a(xKGyDH) => SCxKGyDH | SAxKGyDH"""
    texte = str(row['Sous catégorie']).lower().replace("'", "'").replace(" ", "")
    match = re.search(
        r"surcharge/(carriére|carriere|carrière|annee|annèe|année)\(?(\d+)kg/(\d+)\.000dh\)?",
        texte,
        flags=re.IGNORECASE
    )
    
    if match:
        type_periode = match.group(1)
        poids = match.group(2)
        montant = match.group(3)
        
        if "carri" in type_periode:
            prefixe = f"SC{poids}KG{montant}K"
        elif "ann" in type_periode:
            prefixe = f"SA{poids}KG{montant}K"
        else:
            prefixe = ""
        return row['ID_CONDITION'] + prefixe
    return row['ID_CONDITION']

def ajouter_course_ouverte(row):
    """course ouverte à poids fixe => COPF"""
    texte = str(row['Sous catégorie']).lower().replace("'", "'").replace(" ", "")
    match = re.search(r"courseouverte(?:a|à)poidsfixe", texte, flags=re.IGNORECASE)
    
    if match:
        return row['ID_CONDITION'] + "COPF"
    return row['ID_CONDITION']

def ajouter_jamais_gagne_place(row):
    """N'ayant jamais gagné ni été placé => 0G0P"""
    texte = str(row['Sous catégorie']).lower().replace("'", "'").strip()
    match = re.search(
        r"n.?ayant\s+(?:jamais\s+)?gagn[ée]\s+ni\s+ét[eé]\s+plac[eé]",
        texte,
        flags=re.IGNORECASE
    )
    
    if match:
        return row['ID_CONDITION'] + "0G0P"
    return row['ID_CONDITION']

def ajouter_mois(row):
    """N'ayant jamais gagné/18mois => 0G18M"""
    texte = str(row['Sous catégorie']).lower().replace("'", "'").strip()
    match = re.search(
        r"n'?ayant\s+pas\s+gagn[ée]\s*/\s*(\d+)\s*mois",
        texte,
        flags=re.IGNORECASE
    )
    
    if match:
        duree = match.group(1)
        return row['ID_CONDITION'] + f"0G{duree}M"
    return row['ID_CONDITION']

def ajouter_categorie_course(df):
    """Classe les courses: ARECL, AHAND, ACOND"""
    df['categorie_course'] = np.select(
        [
            df['Remarque'].str.contains('reclamer', case=False, na=False),
            df['Remarque'].str.contains('handicap', case=False, na=False)
        ],
        [
            'ARECL',
            'AHAND'
        ],
        default='ACOND'
    )
    return df

def traiter_codification(df):
    """Traite la codification complète"""
    # Nettoyer d'abord les données
    df = nettoyer_donnees(df)
    
    # Normaliser
    df = normaliser_categories(df)
    
    # Créer ID de base
    df = creer_id_base(df)
    
    # Ajouter suffixes dans l'ordre
    df['ID_CONDITION'] = df.apply(ajouter_suffixe_jamais_gagne, axis=1)
    df['ID_CONDITION'] = df.apply(ajouter_suffixe_x_courses, axis=1)
    df['ID_CONDITION'] = df.apply(ajouter_handicap, axis=1)
    df['ID_CONDITION'] = df.apply(ajouter_suffixe_recu, axis=1)
    df['ID_CONDITION'] = df.apply(ajouter_suffixe_gagne, axis=1)
    df['ID_CONDITION'] = df.apply(ajouter_surcharge, axis=1)
    df['ID_CONDITION'] = df.apply(ajouter_course_ouverte, axis=1)
    df['ID_CONDITION'] = df.apply(ajouter_jamais_gagne_place, axis=1)
    df['ID_CONDITION'] = df.apply(ajouter_mois, axis=1)
    
    # Ajouter catégorie de course
    df = ajouter_categorie_course(df)
    
    return df

def creer_id_enga(row):
    """Crée l'ID pour la jointure: CODE_RACE + CODE_CATEGORIE + CODE_AGE"""
    try:
        return str(row['CODE_RACE_CHEVAL']) + str(row['CODE_CATEGORISATION_COURSE']) + str(row['CODE_AGE_CHEVAL'])
    except:
        return None

def creer_id_programme(row):
    """Crée l'ID standardisé selon Race + Categorie + Age"""
    try:
        race = str(row['Race'])
        cat = str(row['Catégorie']).upper()
        age = str(row['Age'])
        
        # Mapping selon la logique du notebook
        if race == 'AAr' and int(row['Origine']) == 25:
            return 'A2575' + cat[0] + age
        elif race == 'AAr' and int(row['Origine']) == 50:
            return 'AA2A5' + cat[0] + age
        elif race == 'PA':
            return 'PSA' + cat[0] + age
        elif race == 'PS':
            return 'PSAN' + cat[0] + age
        else:
            return race + cat + age
    except:
        return None

def fusionner_avec_engagements(df_prog, df_enga):
    """
    Fusionne les données du programme avec les engagements/partants
    
    Paramètres:
    -----------
    df_prog : DataFrame
        Données du programme des courses avec ID_CONDITION
    df_enga : DataFrame
        Données des engagements et partants
    
    Retour:
    -------
    DataFrame
        Données fusionnées avec engagements et partants
    """
    
    # Préparation df_enga
    df_enga = df_enga.copy()
    
    # Filtrer les catégories valides
    categorias_valides = ['A', 'B', 'C', 'D', 'E']
    df_enga = df_enga[df_enga['CODE_CATEGORISATION_COURSE'].astype(str).str.upper().isin(categorias_valides)]
    
    # Créer ID pour jointure
    df_enga['ID'] = df_enga.apply(creer_id_enga, axis=1)
    
    # Créer categorie_course si nécessaire
    if 'CODE_CATEGORIE_COURSE' in df_enga.columns:
        df_enga['categorie_course'] = df_enga['CODE_CATEGORIE_COURSE']
    elif 'categorie_course' not in df_enga.columns:
        df_enga['categorie_course'] = 'ACOND'
    
    # Renommer colonne de date si nécessaire
    if 'DATE_COURSE' not in df_enga.columns:
        date_cols = [col for col in df_enga.columns if 'date' in col.lower()]
        if date_cols:
            df_enga = df_enga.rename(columns={date_cols[0]: 'DATE_COURSE'})
    
    # Préparation df_prog
    df_prog = df_prog.copy()
    
    # Renommer colonne de date si nécessaire
    for col in df_prog.columns:
        if col == 2025 or (isinstance(col, int)):  # Colonne numérique = date
            df_prog = df_prog.rename(columns={col: 'DATE_COURSE'})
            break
    
    # Créer ID standardisé
    df_prog['ID'] = df_prog.apply(creer_id_programme, axis=1)
    
    # Filtrer les races invalides
    races_invalides = ['AB', 'STEEPLE']
    df_prog = df_prog[~df_prog['Race'].isin(races_invalides)]
    df_enga = df_enga[~df_enga['CODE_RACE_CHEVAL'].astype(str).isin(races_invalides)]
    
    # Fusion sur ID, DATE_COURSE, categorie_course
    try:
        df_merged = pd.merge(
            df_prog, 
            df_enga, 
            on=['ID', 'DATE_COURSE', 'categorie_course'],
            how='inner'
        )
        
        # Ajouter préfixes à ID_CONDITION selon categorie_course
        df_merged['ID_CONDITION'] = df_merged.apply(
            lambda row: ('C' if row['categorie_course'] == 'ACOND' else
                        'R' if row['categorie_course'] == 'ARECL' else
                        'H' if row['categorie_course'] == 'AHAND' else '') + 
                       row['ID_CONDITION'],
            axis=1
        )
        
        return df_merged
    except Exception as e:
        st.error(f"❌ Erreur lors de la fusion: {str(e)}")
        st.warning("Les colonnes requises pour la fusion ne sont pas disponibles.")
        return None

# ============================================================================
# INTERFACE STREAMLIT
# ============================================================================

st.sidebar.markdown("### 📋 Instructions")
st.sidebar.markdown("""
1. Uploadez votre fichier Excel **Programme des courses VF 2025.xlsx**
2. *(Optionnel)* Uploadez le fichier **extract_partant_enga_2025.xlsx**
3. La plateforme va traiter automatiquement les données
4. Consultez et téléchargez les résultats
""")

# Upload des fichiers
col_file1, col_file2 = st.columns(2)

with col_file1:
    st.markdown("### 📁 Fichier Principal")
    uploaded_file = st.file_uploader(
        "Uploadez: Programme des courses",
        type=["xlsx", "xls"],
        help="Fichier Excel contenant les données des courses",
        key="file1"
    )

with col_file2:
    st.markdown("### 📁 Fichier Optionnel")
    uploaded_enga = st.file_uploader(
        "Uploadez: Engagements et Partants (optionnel)",
        type=["xlsx", "xls"],
        help="Fichier contenant nombre d'engagements et partants",
        key="file2"
    )

if uploaded_file is not None:
    try:
        # Lire le fichier principal
        with st.spinner("📖 Lecture du fichier programme..."):
            df = pd.read_excel(uploaded_file)
            # Nettoyer immédiatement après le chargement
            df = nettoyer_donnees(df)
        
        st.success(f"✅ Fichier programme chargé ({len(df)} lignes)")
        
        # Lire le fichier engagements si fourni
        df_merged = None
        if uploaded_enga is not None:
            with st.spinner("📖 Lecture du fichier engagements..."):
                df_enga = pd.read_excel(uploaded_enga)
            
            st.success(f"✅ Fichier engagements chargé ({len(df_enga)} lignes)")
        
        # Afficher aperçu
        with st.expander("👀 Aperçu des données brutes"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Programme des courses:**")
                st.dataframe(df.head(5), use_container_width=True)
            if uploaded_enga is not None:
                with col2:
                    st.markdown("**Engagements et Partants:**")
                    st.dataframe(df_enga.head(5), use_container_width=True)
        
        # Traiter la codification
        with st.spinner("⚙️ Traitement de la codification..."):
            df_traite = traiter_codification(df.copy())
        
        st.success("✅ Codification complète!")
        
        # Fusionner avec engagements si disponible
        if uploaded_enga is not None:
            with st.spinner("🔗 Fusion avec engagements..."):
                df_merged = fusionner_avec_engagements(df_traite.copy(), df_enga)
            
            if df_merged is not None:
                st.success(f"✅ Fusion réussie ({len(df_merged)} lignes)")
                df_traite = df_merged
            else:
                st.warning("⚠️ La fusion n'a pas pu être effectuée. Affichage des résultats sans engagements.")
        
        # Éliminer les doublons exacts (même ID_CONDITION + même date_course)
        date_col = None
        for col in df_traite.columns:
            col_str = str(col).lower()
            if 'date' in col_str or col == 2025 or 'DATE_COURSE' in str(col):
                date_col = col
                break
        
        if date_col:
            nb_avant = len(df_traite)
            # Garder une seule occurrence pour chaque combinaison ID_CONDITION + date
            df_traite = df_traite.drop_duplicates(subset=['ID_CONDITION', date_col], keep='first').reset_index(drop=True)
            nb_apres = len(df_traite)
            
            if nb_avant > nb_apres:
                st.info(f"🗑️ {nb_avant - nb_apres} doublons exacts supprimés (même ID_CONDITION + même date)")
        
        # Afficher résultats
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("### 📊 Statistiques")
            st.metric("Nombre de courses", len(df_traite))
            st.metric("Codes uniques générés", df_traite['ID_CONDITION'].nunique())
        
        with col2:
            st.markdown("### 📈 Catégories")
            st.metric("Catégories de courses", df_traite['categorie_course'].nunique())
            cat_dist = df_traite['categorie_course'].value_counts()
            st.bar_chart(cat_dist)
        
        with col3:
            st.markdown("### 📋 Engagements & Partants")
            if df_merged is not None:
                if 'NBR_ENGAGEMENT' in df_traite.columns:
                    st.metric(
                        "Engagements moyens",
                        f"{df_traite['NBR_ENGAGEMENT'].mean():.1f}"
                    )
                if 'NBR_PARTANT' in df_traite.columns:
                    st.metric(
                        "Partants moyens",
                        f"{df_traite['NBR_PARTANT'].mean():.1f}"
                    )
            else:
                st.info("Uploadez un fichier d'engagements pour voir ces stats.")
        
        # ============================================================================
        # ANALYSE DES DOUBLONS PAR ID_CONDITION
        # ============================================================================
        st.markdown("---")
        st.markdown("### 🔍 Analyse des Doublons par ID_CONDITION")
        
        # Identifier les doublons
        doublons = df_traite.groupby('ID_CONDITION').size().reset_index(name='Nombre_Occurrences')
        doublons = doublons[doublons['Nombre_Occurrences'] > 1].sort_values('Nombre_Occurrences', ascending=False)
        
        # Initialiser la variable à None (sera remplie si doublons existent)
        df_doublons_detail = None
        
        if len(doublons) > 0:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Codes dupliqués", len(doublons))
            with col2:
                st.metric("Total d'occurrences dupliquées", doublons['Nombre_Occurrences'].sum())
            with col3:
                st.metric("Occurrence maximale", doublons['Nombre_Occurrences'].max())
            
            # Tableau des doublons avec marge de dates
            st.markdown("#### 📅 Détail des doublons et écarts de dates")
            
            doublons_detail = []
            date_col = None
            
            # Détecter la colonne de date
            for col in df_traite.columns:
                col_str = str(col).lower()
                if 'date' in col_str or col == 2025 or 'DATE_COURSE' in str(col):
                    date_col = col
                    break
            
            for idx, row in doublons.iterrows():
                id_cond = row['ID_CONDITION']
                occurrences = df_traite[df_traite['ID_CONDITION'] == id_cond]
                nb_occur = len(occurrences)
                
                # Calculer les écarts de dates si disponible
                if date_col and date_col in df_traite.columns:
                    try:
                        # Convertir en datetime avec gestion d'erreurs robuste
                        dates_raw = occurrences[date_col]
                        dates = pd.to_datetime(dates_raw, errors='coerce').dropna().sort_values()
                        
                        if len(dates) > 1:
                            first_date = dates.iloc[0]
                            last_date = dates.iloc[-1]
                            dates_str = f"{first_date.strftime('%d/%m/%Y')} → {last_date.strftime('%d/%m/%Y')}"
                            
                            # Calculer le minimum écart entre deux dates consécutives
                            ecarts = []
                            for i in range(len(dates) - 1):
                                ecart = (dates.iloc[i + 1] - dates.iloc[i]).days
                                ecarts.append(ecart)
                            
                            if ecarts:
                                ecart_jours = min(ecarts)
                                ecart_mois = round(ecart_jours / 30.44, 1)
                            else:
                                ecart_jours = None
                                ecart_mois = None
                        else:
                            ecart_jours = None
                            ecart_mois = None
                            dates_str = "N/A"
                    except Exception as e:
                        # Gestion d'erreurs silencieuse
                        ecart_jours = None
                        ecart_mois = None
                        dates_str = "N/A"
                else:
                    ecart_jours = None
                    ecart_mois = None
                    dates_str = "N/A"
                
                doublons_detail.append({
                    'ID_CONDITION': id_cond,
                    'Nombre de fois': nb_occur,
                    'Plage de dates': dates_str,
                    'Écart (jours)': ecart_jours,
                    'Écart (mois)': ecart_mois
                })
            
            df_doublons_detail = pd.DataFrame(doublons_detail)
            st.dataframe(df_doublons_detail, use_container_width=True)
            
            # Visualisation
            st.markdown("#### 📊 Graphique des occurrences")
            chart_data = doublons.head(15).sort_values('Nombre_Occurrences', ascending=True)
            st.bar_chart(chart_data.set_index('ID_CONDITION')['Nombre_Occurrences'])
            
            # ============================================================================
            # SECTION INTERACTIVE: Détail des doublons
            # ============================================================================
            st.markdown("---")
            st.markdown("#### 🔎 Détail interactif - Sélectionnez un code")
            
            # Sélectionner un ID_CONDITION
            id_selected = st.selectbox(
                "Choisissez un code à analyser:",
                options=sorted(df_doublons_detail['ID_CONDITION'].unique()),
                help="Cliquez pour voir tous les enregistrements de ce code"
            )
            
            if id_selected:
                # Récupérer tous les enregistrements de ce code
                records_selected = df_traite[df_traite['ID_CONDITION'] == id_selected].copy()
                
                # Trouver la colonne de date
                date_col = None
                for col in records_selected.columns:
                    col_str = str(col).lower()
                    if 'date' in col_str or col == 2025 or 'DATE_COURSE' in str(col):
                        date_col = col
                        break
                
                # Trier par date si disponible
                if date_col and date_col in records_selected.columns:
                    try:
                        records_selected[date_col] = pd.to_datetime(records_selected[date_col], errors='coerce')
                        records_selected = records_selected.sort_values(date_col, ascending=True)
                    except:
                        pass
                
                # Afficher les détails
                st.markdown(f"**Code sélectionné:** `{id_selected}`")
                st.markdown(f"**Nombre d'occurrences:** {len(records_selected)}")
                
                # Colonnes à afficher
                cols_to_show = ['ID_CONDITION']
                
                # Ajouter la colonne date si elle existe
                if date_col:
                    cols_to_show.append(date_col)
                
                # Ajouter les colonnes importantes
                for col in ['Catégorie', 'Age', 'Origine', 'Race', 'Sous catégorie']:
                    if col in records_selected.columns:
                        cols_to_show.append(col)
                
                # Ajouter engagements/partants si disponibles
                for col in ['NBR_ENGAGEMENT', 'NBR_PARTANT', 'NOM_PRIX', 'CODE_COURSE']:
                    if col in records_selected.columns:
                        cols_to_show.append(col)
                
                # Afficher le tableau
                st.markdown("**📋 Tous les enregistrements (triés de ancien vers récent):**")
                
                display_df = records_selected[cols_to_show].copy()
                
                # Formater la date si elle existe
                if date_col and date_col in display_df.columns:
                    try:
                        display_df[date_col] = display_df[date_col].dt.strftime('%d/%m/%Y')
                    except:
                        pass
                
                st.dataframe(display_df, use_container_width=True)
                
                # Statistiques additionnelles si engagements disponibles
                if 'NBR_ENGAGEMENT' in records_selected.columns and 'NBR_PARTANT' in records_selected.columns:
                    st.markdown("---")
                    st.markdown("**📊 Statistiques engagements & partants:**")
                    
                    col1, col2, col3, col4, col5 = st.columns(5)
                    
                    with col1:
                        st.metric(
                            "Engagements moyens",
                            f"{records_selected['NBR_ENGAGEMENT'].mean():.1f}"
                        )
                    with col2:
                        st.metric(
                            "Engagements max",
                            f"{int(records_selected['NBR_ENGAGEMENT'].max())}"
                        )
                    with col3:
                        st.metric(
                            "Partants moyens",
                            f"{records_selected['NBR_PARTANT'].mean():.1f}"
                        )
                    with col4:
                        st.metric(
                            "Partants max",
                            f"{int(records_selected['NBR_PARTANT'].max())}"
                        )
                    with col5:
                        taux_part = (records_selected['NBR_PARTANT'].mean() / records_selected['NBR_ENGAGEMENT'].mean() * 100)
                        st.metric(
                            "Taux participation",
                            f"{taux_part:.1f}%"
                        )
                    
                    # Graphique évolution des engagements/partants
                    if date_col and date_col in records_selected.columns:
                        st.markdown("**📈 Évolution engagements & partants:**")
                        
                        evolution_df = records_selected[[date_col, 'NBR_ENGAGEMENT', 'NBR_PARTANT']].copy()
                        # Convertir en datetime et garder l'ordre chronologique
                        evolution_df[date_col] = pd.to_datetime(evolution_df[date_col], errors='coerce')
                        evolution_df = evolution_df.dropna(subset=[date_col])  # Supprimer les dates invalides
                        evolution_df = evolution_df.sort_values(date_col, ascending=True)  # Trier du plus ancien au plus récent
                        # Garder le datetime comme index (pas de formatage texte qui casse le tri)
                        evolution_df = evolution_df.set_index(date_col)
                        
                        st.line_chart(evolution_df)
            
        else:
            st.info("✅ Aucun doublon détecté! Chaque ID_CONDITION est unique.")
        
        # ============================================================================
        # ANALYSE DES ENGAGEMENTS ET PARTANTS
        # ============================================================================
        if df_merged is not None and 'NBR_ENGAGEMENT' in df_traite.columns:
            st.markdown("---")
            st.markdown("###  Analyse des Engagements et Partants")
            
            # Statistiques globales
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Engagement moyen",
                    f"{df_traite['NBR_ENGAGEMENT'].mean():.1f}"
                )
            with col2:
                st.metric(
                    "Engagement max",
                    f"{int(df_traite['NBR_ENGAGEMENT'].max())}"
                )
            with col3:
                st.metric(
                    "Partants moyen",
                    f"{df_traite['NBR_PARTANT'].mean():.1f}"
                )
            with col4:
                st.metric(
                    "Partants max",
                    f"{int(df_traite['NBR_PARTANT'].max())}"
                )
            
            # Analyse par ID_CONDITION
            st.markdown("#### 📊 Top conditions par engagements")
            
            analyse_enga = (
                df_traite.groupby(['ID_CONDITION', 'Race'], as_index=False)
                .agg({
                    'NBR_ENGAGEMENT': ['mean', 'count'],
                    'NBR_PARTANT': 'mean'
                })
                .rename(columns={
                    ('NBR_ENGAGEMENT', 'mean'): 'Engagement_Moyen',
                    ('NBR_ENGAGEMENT', 'count'): 'Occurrences',
                    ('NBR_PARTANT', 'mean'): 'Partants_Moyen'
                })
            )
            
            # Aplatir les colonnes multi-niveaux
            analyse_enga.columns = ['ID_CONDITION', 'Race', 'Engagement_Moyen', 'Occurrences', 'Partants_Moyen']
            analyse_enga = analyse_enga.sort_values('Engagement_Moyen', ascending=False)
            
            st.dataframe(analyse_enga.head(20), use_container_width=True)
            
            # Visualisations
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### 📈 Distribution des engagements")
                st.line_chart(
                    df_traite['NBR_ENGAGEMENT'].value_counts().sort_index()
                )
            
            with col2:
                st.markdown("#### 📈 Distribution des partants")
                st.line_chart(
                    df_traite['NBR_PARTANT'].value_counts().sort_index()
                )
        
        # ============================================================================
        # RÉSULTATS DÉTAILLÉS
        # ============================================================================
        st.markdown("---")
        st.markdown("### 📋 Résultats complets")
        st.dataframe(df_traite, use_container_width=True)
        
        # Export
        st.markdown("---")
        st.markdown("### 💾 Téléchargement")
        
        # Créer un fichier Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_traite.to_excel(writer, sheet_name='Codification', index=False)
            
            # Ajouter un sheet d'analyse par race
            analyse = (
                df_traite.groupby(['ID_CONDITION', 'Race'], as_index=False)
                .agg({
                    'ID_CONDITION': 'count'
                })
                .rename(columns={'ID_CONDITION': 'Occurrences'})
                .sort_values('Occurrences', ascending=False)
            )
            analyse.to_excel(writer, sheet_name='Analyse', index=False)
            
            # Ajouter sheet d'analyse des doublons si disponible
            if df_doublons_detail is not None:
                df_doublons_detail.to_excel(writer, sheet_name='Doublons', index=False)
            
            # NOUVEAU: Ajouter sheet d'analyse des engagements/partants
            if df_merged is not None and 'NBR_ENGAGEMENT' in df_traite.columns:
                analyse_enga = (
                    df_traite.groupby(['ID_CONDITION', 'Race'], as_index=False)
                    .agg({
                        'ID_CONDITION': 'count',
                        'NBR_ENGAGEMENT': 'mean',
                        'NBR_PARTANT': 'mean'
                    })
                    .rename(columns={
                        'ID_CONDITION': 'Occurrences',
                        'NBR_ENGAGEMENT': 'Engagement_Moyen',
                        'NBR_PARTANT': 'Partants_Moyen'
                    })
                    .sort_values('Occurrences', ascending=False)
                )
                analyse_enga.to_excel(writer, sheet_name='Engagements', index=False)
        
        output.seek(0)
        
        st.download_button(
            label="📥 Télécharger les résultats (Excel)",
            data=output.getvalue(),
            file_name="codification_resultats.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # CSV export
        csv = df_traite.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Télécharger en CSV",
            data=csv,
            file_name="codification_resultats.csv",
            mime="text/csv"
        )
        
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.info("Assurez-vous que le fichier contient les colonnes requises: Catégorie, Age, Origine, Race, Sous catégorie, Remarque")

else:
    st.info("👆 Veuillez uploader un fichier pour commencer")
    
    # Exemple de colonnes requises
    st.markdown("### 📝 Colonnes requises")
    
    with st.expander("📄 Fichier Programme des courses"):
        required_cols = pd.DataFrame({
            'Colonne': ['Catégorie', 'Age', 'Origine', 'Race', 'Sous catégorie', 'Remarque', 'DATE_COURSE (optionnel)'],
            'Description': [
                'Catégorie de la course (A, B, C, D, E, ...)',
                'Âge requis',
                'Origine du cheval (numérique, ex: 25, 50)',
                'Race du cheval (AAr, PA, PS, ...)',
                'Conditions spécifiques',
                'Notes et remarques additionnelles',
                'Date de la course (optionnelle)'
            ]
        })
        st.dataframe(required_cols, use_container_width=True)
    
    with st.expander("📄 Fichier Engagements (optionnel)"):
        enga_cols = pd.DataFrame({
            'Colonne': [
                'CODE_RACE_CHEVAL',
                'CODE_CATEGORISATION_COURSE',
                'CODE_AGE_CHEVAL',
                'DATE_COURSE',
                'NBR_ENGAGEMENT',
                'NBR_PARTANT',
                'CODE_CATEGORIE_COURSE'
            ],
            'Description': [
                'Code race du cheval (AAr, PA, PS, ...)',
                'Catégorie de la course (A, B, C, D, E)',
                'Âge du cheval',
                'Date de la course',
                'Nombre d\'engagements',
                'Nombre de partants',
                'Catégorie de course (ACOND, ARECL, AHAND)'
            ]
        })
        st.dataframe(enga_cols, use_container_width=True)
