# app/pages/4_analyse_utilisateurs.py
import io
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import matplotlib.pyplot as plt
import numpy as np

from utils_docs import hide_native_nav, custom_sidebar_nav, sidebar_system_status, require_login
from analytics.user_behavior import (
    load_logs_df, compute_ratios, aggregate_by_application,
    auto_k_elbow, cluster_with_k, cluster_centers_mean,
    modules_by_application
)

from analytics.user_behavior import user_active_days_total, top_users_by_days, low_engagement_users


# --- Page setup & chrome ---
st.set_page_config(page_title="Analyse utilisateurs", layout="wide")
hide_native_nav()
custom_sidebar_nav()
require_login()
sidebar_system_status()

st.title(" Analyse du comportement utilisateur dans MasterControl")

st.markdown(
    """
    <div style="
        background-color: #e6f2ff;
        border: 1px solid #b3d1ff;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 20px;
    ">
        <h3 style="color:#1b74b8;">Démarche d’analyse</h3>
        <p>
        Cette analyse propose d’évaluer le comportement des utilisateurs dans l'environnemnt MasterControl.
        L’approche combine deux volets complémentaires :
        </p>
        <ul>
            <li><b>Clustering des profils utilisateurs</b> : à partir des logs (activités par application et module), des ratios d’utilisation sont calculés et regroupés en clusters de profils homogènes par la méthode du K-Means.</li>
            <li><b>Analyse descriptive de l’activité</b> : mesure de la fréquence de connexion (jours actifs distincts), identification des super-users, et détection des utilisateurs peu ou pas actifs.</li>
        </ul>
           
       
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <div style="background:#eef6ff;border:1px solid #cfe3ff;border-radius:12px;padding:16px;margin:6px 0 10px 0;">
      <div style="font-size:20px;font-weight:700;color:#0e4f7c;margin-bottom:6px;">
        Import des logs MasterControl (CSV)
      </div>
      <div style="font-size:16px;line-height:1.5;color:#0e4f7c;">
        <b>ATTENTION :</b> la table doit contenir <u>dans l’ordre exact</u> les colonnes :
        <b>Application</b>, <b>Module</b>, <b>User ID</b>, <b>Date</b>.
      </div>
    </div>
    """,
    unsafe_allow_html=True
)
uploaded = st.file_uploader(
    "Dépose l’export CSV",
    type=["csv"],
    label_visibility="collapsed"  
)
if not uploaded:
    st.info("Charge un CSV pour continuer.")
    st.stop()

# --- Chargement du CSV ---
try:
    df = load_logs_df(uploaded)
except Exception as e:
    st.error(f"Erreur de chargement: {e}")
    st.stop()

with st.expander("Aperçu des données (5 lignes)"):
    st.dataframe(df.head(), use_container_width=True)

# --- Période couverte ---
date_min = df["Date"].min()
date_max = df["Date"].max()


# --- Calcule des Ratios par (Application, Module) puis agrégation par Application 
with st.spinner("Calcul des ratios par utilisateur…"):
    df_profiles = compute_ratios(df)                   # colonnes = (Application, Module)
    ratios_app = aggregate_by_application(df_profiles) # colonnes = Applications (agrégé)

st.success(
    f"📅 Données disponibles du **{date_min}** au **{date_max}**\n\n"
    f"La matrice de travail pour le clustering contient {ratios_app.shape[0]} utilisateurs "
    f"et {ratios_app.shape[1]} applications. "
    )

st.info("""
Le **clustering K-Means** est une méthode de regroupement automatique :  
l’algorithme prend tous les utilisateurs et les rassemble en *K groupes* qui se ressemblent. Chaque groupe correspond à un profil d’utilisation.

Mais comment choisir le bon nombre de groupes K ?  
On utilise la **méthode du coude** : on fait tourner l’algorithme avec différents K et on regarde la courbe de performance. Quand la courbe "se plie" comme un coude,  
cela indique le K optimal : ajouter plus de groupes n’apporte plus vraiment d’information.
            
Même si la méthode du coude suggère une valeur, on peut aussi **ajuster K selon la vision métier**. Par exemple, si vous voulez comparer 3 grands types d’utilisateurs, vous pouvez fixer K=3,  
même si la courbe propose une autre valeur.
""")

# --- K automatique (Elbow 1→10) ---
with st.spinner("Méthode du coude (distorsion) sur les applications…"):
    k_auto, viz = auto_k_elbow(ratios_app, k_min=1, k_max=10)

# Courbe du coude + K détecté à gauche
col1, col2 = st.columns([0.5, 0.5])
with col1:
    st.success(f"K détecté (intra-app) : **{k_auto}**")
    st.pyplot(viz.fig, use_container_width=True)

# --- Clustering initial avec K auto (pas de message 'clustering terminé') ---
with st.spinner(f"Clustering KMeans (K={int(k_auto)})…"):
    df_app_labeled, labels = cluster_with_k(ratios_app, int(k_auto))

# --- Heatmap centres (résultat avec K auto) ---
st.subheader("Profils moyens par cluster (Applications)")
centers = cluster_centers_mean(df_app_labeled)
centers_plot = centers.copy()
centers_plot.index.name = "Cluster"

fig_hm = px.imshow(
    centers_plot,
    aspect="auto",
    labels=dict(x="Application", y="Cluster", color="Proportion d’activité"),
    color_continuous_scale="Blues",
    text_auto=".2f",
    zmin=0, zmax=1,
)
fig_hm.update_yaxes(
    tickmode="array",
    tickvals=list(range(len(centers_plot.index))),
    ticktext=[str(i) for i in centers_plot.index],
)
fig_hm.update_layout(
    height=300 + 30 * len(centers_plot.index),
    margin=dict(l=40, r=40, t=40, b=40),
)
st.plotly_chart(fig_hm, use_container_width=True)

# --- Réglage manuel de K (SOUS la heatmap) ---
# --- Colonnage pour les étapes de réglage/lecture ---
col_left, col_right = st.columns([0.5, 0.5])

with col_left:
    # 1) K manuel — UN SEUL number_input
    n_users = ratios_app.shape[0]
    k_upper = max(2, min(10, n_users - 1))
    k_default = min(max(2, int(k_auto)), k_upper)

    k_use = st.number_input(
        "Modifier le nombre de clusters (K) si besoin :",
        min_value=2, max_value=k_upper, value=k_default, step=1,
        key="global_kmanual",
    )

    # ⬇️ Recalcule si K change (et met à jour centers_plot + fig_hm pour l’export)
    if int(k_use) != int(k_auto):
        df_app_labeled, labels = cluster_with_k(ratios_app, int(k_use))
        centers = cluster_centers_mean(df_app_labeled)
        centers_plot = centers.copy()
        centers_plot.index.name = "Cluster"

        fig_hm = px.imshow(
            centers_plot,
            aspect="auto",
            labels=dict(x="Application", y="Cluster", color="Proportion d’activité"),
            color_continuous_scale="Blues",
            text_auto=".2f",
            zmin=0, zmax=1,
        )
        fig_hm.update_yaxes(
            tickmode="array",
            tickvals=list(range(len(centers_plot.index))),
            ticktext=[str(i) for i in centers_plot.index],
        )
        fig_hm.update_layout(
            height=300 + 30 * len(centers_plot.index),
            margin=dict(l=40, r=40, t=40, b=40),
        )
        st.plotly_chart(fig_hm, use_container_width=True)

    # 2) Taille des clusters (Application)
    sizes_global = df_app_labeled["cluster"].value_counts().sort_index()
    st.caption("Taille des clusters (Application)")
    tbl = sizes_global.to_frame("Users").reset_index().rename(columns={"index": "Cluster"})
    st.dataframe(
        tbl, use_container_width=True, hide_index=True,
        column_config={
            "Cluster": st.column_config.NumberColumn(format="%d", width="small"),
            "Users":   st.column_config.NumberColumn(format="%d", width="small"),
        },
    )

    # 3) Tableau des centres (ratios moyens)
    with st.expander("Tableau des centres (ratios moyens)"):
        st.dataframe(centers_plot, use_container_width=True)

with col_right:
    # ( laisser vide )
    pass


# --- Export ---
st.subheader("Exports")
buf_csv = io.StringIO()
df_app_labeled.reset_index().rename(columns={"index": "User ID"}).to_csv(buf_csv, index=False)
st.download_button(
    "📥 Télécharger les labels par user (CSV)",
    data=buf_csv.getvalue(),
    file_name="clusters_users.csv",
    mime="text/csv"
)

# --- Export heatmap Application (HTML ) -------------------------------------------------------
html_str = fig_hm.to_html(full_html=False, include_plotlyjs="cdn")
st.download_button(
    "📥 Exporter la heatmap (HTML)",
    data=html_str,
    file_name="heatmap_clusters.html",
    mime="text/html",
    key="dl_hm_html",
)
st.caption("ℹ️ L’export correspond à la dernière heatmap affichée (K automatique ou K manuel).")

#------------------------------------------------------------------------------------------------------------------------------------------#
st.header("🔬 Clustering intra-application (modules)")
#------------------------------------------------------------------------------------------------------------------------------------------#

# ── Option : analyse intra-application (par modules)----------------------------------------------
choice_intra = st.radio(
    "Voulez-vous analyser une application en détail ?",
    options=["Non", "Oui"],
    index=0,
    horizontal=True,
    key="intra_toggle"
)

if choice_intra == "Oui":
    # Choix de l’appli à zoomer--------------------------------------------------------------------
    apps = sorted({lvl0 for (lvl0, lvl1) in df_profiles.columns})
    app = st.selectbox("Application à analyser :", apps, key="intra_app_selector")

    # Sous-matrice modules de l’appli choisie-------------------------------------------------------
    df_app_mod = df_profiles[app].copy()
    df_app_mod = df_app_mod.loc[df_app_mod.sum(axis=1) > 0, :]
    df_app_mod = df_app_mod.loc[:, df_app_mod.sum(axis=0) > 0]

    # PAs d'analyse si moins de 2 colonnes-----------------------------------------------------------
    if df_app_mod.empty or df_app_mod.shape[0] < 20 or df_app_mod.shape[1] < 2:
        st.warning("Pas assez de signal sur cette application (moins de 20 utilisateurs ou moins de 2 modules actifs).")
        st.stop()

    # Coude auto 1→10 (borné) puis layout 2 colonnes
    n_users = df_app_mod.shape[0]
    k_max_intra = min(10, max(2, n_users - 1))
    with st.spinner("Méthode du coude (distorsion) sur l’application…"):
        k_auto_intra, viz_intra = auto_k_elbow(df_app_mod, k_min=1, k_max=k_max_intra)

    col1, col2 = st.columns([0.5, 0.5])
    with col1:
        st.success(f"K détecté (intra-app) : **{k_auto_intra}**")
        st.pyplot(viz_intra.fig, use_container_width=True)

# --- Clustering initial avec K auto ---
    with st.spinner(f"Clustering KMeans (K={int(k_auto_intra)})…"):
        df_app_mod_labeled, labels_intra = cluster_with_k(df_app_mod, int(k_auto_intra))

    centers_intra = cluster_centers_mean(df_app_mod_labeled).copy()
    centers_intra.index.name = "Cluster"

    import plotly.express as px
    fig_hm_intra = px.imshow(
        centers_intra,
        aspect="auto",
        labels=dict(x="Module", y="Cluster", color="Proportion d’activité"),
        color_continuous_scale="Blues",
        text_auto=".2f", zmin=0, zmax=1,
)
    fig_hm_intra.update_yaxes(
        tickmode="array",
        tickvals=list(range(len(centers_intra.index))),
        ticktext=[str(i) for i in centers_intra.index],
)
    fig_hm_intra.update_layout(
        height=300 + 30 * len(centers_intra.index),
        margin=dict(l=40, r=40, t=40, b=40),
        title_text=f"Profils moyens par module — {app}",
)
    st.plotly_chart(fig_hm_intra, use_container_width=True)

# --- Réglage manuel de K (SOUS la heatmap) ---
    col_left_intra, col_right_intra = st.columns([0.5, 0.5])

    with col_left_intra:
    # 1) K manuel — UN SEUL number_input (intra)
        k_default_intra = min(max(2, int(k_auto_intra)), k_max_intra)
        k_use_intra = st.number_input(
            "Modifier le nombre de clusters (K) si besoin (intra-app) :",
            min_value=2, max_value=k_max_intra, value=k_default_intra, step=1,
            key=f"intra_kmanual_{app}",  # clé unique par application
    )

        # ⬇️ Recalcule si K change (et met à jour centers_intra + fig_hm_intra pour l’export)
        if int(k_use_intra) != int(k_auto_intra):
            df_app_mod_labeled, labels_intra = cluster_with_k(df_app_mod, int(k_use_intra))
            centers_intra = cluster_centers_mean(df_app_mod_labeled).copy()
            centers_intra.index.name = "Cluster"

            import plotly.express as px
            fig_hm_intra = px.imshow(
                centers_intra,
                aspect="auto",
                labels=dict(x="Module", y="Cluster", color="Proportion d’activité"),
                color_continuous_scale="Blues",
                text_auto=".2f", zmin=0, zmax=1,
        )
            fig_hm_intra.update_yaxes(
                tickmode="array",
                tickvals=list(range(len(centers_intra.index))),
                ticktext=[str(i) for i in centers_intra.index],
        )
            fig_hm_intra.update_layout(
                height=300 + 30 * len(centers_intra.index),
                margin=dict(l=40, r=40, t=40, b=40),
                title_text=f"Profils moyens par module — {app} (K={int(k_use_intra)})",
        )
            st.plotly_chart(fig_hm_intra, use_container_width=True)

    # 2) Taille des clusters (module)
        sizes_intra = df_app_mod_labeled["cluster"].value_counts().sort_index()
        st.caption("Taille des clusters (module)")
        tbl_intra = sizes_intra.to_frame("Users").reset_index().rename(columns={"index": "Cluster"})
        st.dataframe(
            tbl_intra,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Cluster": st.column_config.NumberColumn(format="%d", width="small"),
                "Users":   st.column_config.NumberColumn(format="%d", width="small"),
        },
    )

    # 3) Tableau des centres (ratios moyens) — intra
        with st.expander("Tableau des centres (ratios moyens) — intra-app"):
            st.dataframe(centers_intra, use_container_width=True)

    with col_right:
     # (laisser vide )
        pass


# --- Export ---
    st.subheader("Exports")
    buf_csv_intra = io.StringIO()
    df_app_mod_labeled.reset_index().rename(columns={"index": "User ID"}).to_csv(buf_csv_intra, index=False)
    st.download_button(
        "📥 Télécharger les labels par user (CSV)",
        data=buf_csv_intra.getvalue(),
        file_name=f"clusters_users_{app}.csv",
        mime="text/csv",
        key=f"dl_labels_intra_csv_{app}",
)

# --- Export heatmap Application (HTML ) -------------------------------------------------------
    html_str = fig_hm_intra.to_html(full_html=False, include_plotlyjs="cdn")
    st.download_button(
        "📥 Exporter la heatmap (HTML)",
        data=html_str,
        file_name="heatmap_clusters.html",
        mime="text/html",
        key="dl_hm_html_global", 
)
    st.caption("ℹ️ L’export correspond à la dernière heatmap affichée (K automatique ou K manuel).")



else:
    st.caption("Activez l’analyse intra-application pour explorer les modules d’une application précise.")







#-----------------------------------------------------------------------------------------------------------------------------------#
from analytics.user_behavior import user_active_days_total, top_users_by_days, low_engagement_users
#-----------------------------------------------------------------------------------------------------------------------------------#
# --- Résumé méthodologique pour l'analyse par connexions ---
st.markdown(
    """
    <div style="
        background-color: #e6f2ff;
        border: 1px solid #b3d1ff;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 20px;
    ">
        <h3 style="color:#1b74b8;">📆 Analyse par connexions (jours actifs distincts)</h3>
        <p>
        En complément du clustering, cette étape mesure la <b>régularité d’utilisation</b>.
        On compte le nombre de <b>jours distincts d’activité</b> par utilisateur :
        </p>
        <ul>
            <li>Un utilisateur est considéré actif un jour donné dès qu’il réalise au moins une action,
            <i>peu importe l’application ou le module</i>.</li>
            <li>Cette métrique est moins sensible au volume de logs, et donne une vision plus fiable
            de la <b>fréquence réelle de connexion</b>.</li>
            <li>On peut ainsi identifier :
                <ul>
                    <li>la distribution du nombre de connexion,</li>
                    <li>les <b>super-users</b> très réguliers,</li>
                    <li>les <b>utilisateurs à faible engagement</b> ou inactifs.</li>
                </ul>
        
    </div>
    """,
    unsafe_allow_html=True
)


s_days = user_active_days_total(df)  # df = CSV brut déjà chargé plus haut

# Bar chart : TOUS les users, triés, sans étiquettes X
plot_data = s_days.reset_index()
plot_data.columns = ["User ID", "Distinct active days"]  # s_days est déjà trié décroissant

fig_days = px.bar(
    plot_data,
    x="User ID",
    y="Distinct active days",
    title="Jours actifs distincts par utilisateur (tous les users, tri décroissant)",
    labels={"User ID": "User", "Distinct active days": "Jours actifs"}
)
fig_days.update_xaxes(showticklabels=False)  # masque toutes les étiquettes X
fig_days.update_layout(bargap=0.2)
#  hover pour lire l’ID + valeur
fig_days.update_traces(hovertemplate="User: %{x}<br>Jours actifs: %{y}<extra></extra>")

st.plotly_chart(fig_days, use_container_width=True)



# Top 10 super users------------------------------------------------------------------
st.subheader("🏆 Top 10 — Super users (jours actifs)")
df_top10 = top_users_by_days(s_days, top_n=10)
col_left, _ = st.columns([0.3, 0.7])  # 30% gauche, 70% vide/droite
with col_left:
    st.dataframe(
        df_top10,
        use_container_width=True,
        hide_index=True,
        column_config={
            "User ID": st.column_config.TextColumn(width="small"),
            "distinct_active_days": st.column_config.NumberColumn(format="%d", width="small"),
        },
    )


# Faible engagement--------------------------------------------------------------------
st.subheader("⬇️ Utilisateurs à faible engagement")
mode = st.radio("Mode de sélection du seuil", ["Absolu (X jours)", "Quantile (% les plus faibles)"], horizontal=True)
col_a, col_b = st.columns(2)

if mode.startswith("Absolu"):
    with col_a:
        X = st.number_input("Seuil X (jours)", min_value=0, value=3, step=1)
    df_low, thr = low_engagement_users(s_days, mode="absolute", x=int(X))
    st.caption(f"Sélection: utilisateurs avec **jours actifs ≤ {thr}**.")
else:
    with col_a:
        pct = st.slider("Quantile (%)", min_value=1, max_value=50, value=10, step=1)
    df_low, thr = low_engagement_users(s_days, mode="quantile", q=float(pct)/100.0)
    st.caption(f"Sélection: **{pct}%** les plus faibles (seuil calculé: **≤ {thr} jours**).")

col_left, _ = st.columns([0.3, 0.7])
with col_left:
    st.dataframe(
        df_low,
        use_container_width=True,
        hide_index=True,
        column_config={
            "User ID": st.column_config.TextColumn(width="small"),
            "distinct_active_days": st.column_config.NumberColumn(format="%d", width="small"),
        },
    )

# Exports ------------------------------------------------------------------------------
col_dl1, col_dl2 = st.columns(2)
with col_dl1:
    csv_top = df_top10.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Export Top 10 (CSV)", data=csv_top, file_name="top10_super_users.csv", mime="text/csv")
with col_dl2:
    csv_low = df_low.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Export Low Engagement (CSV)", data=csv_low, file_name="low_engagement_users.csv", mime="text/csv")
