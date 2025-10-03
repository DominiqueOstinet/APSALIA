# analytics/user_behavior.py
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Tuple, Dict, List
from sklearn.cluster import KMeans
from types import SimpleNamespace

# Colonnes exigées par l'export consolidé
REQUIRED_COLUMNS = ["Application", "Module", "User ID", "Date"]


def load_logs_df(uploaded_file) -> pd.DataFrame:
    """
    Charge le CSV consolidé (Application, Module, User ID, Date).
    Gère séparateurs (comma/semicolon/tab), BOM et espaces.
    """
   
    # Lecture directe avec autodétection du séparateur
    df = pd.read_csv(
        uploaded_file,
        sep=None,
        engine="python",
        dtype=str,
        keep_default_na=False
    )

    # Nettoyage des noms de colonnes
    df.columns = (
        df.columns
        .str.replace("\ufeff", "", regex=False)  # retire BOM éventuel
        .str.strip()
    )

    required = ["Application", "Module", "User ID", "Date"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes: {missing} — détectées: {list(df.columns)}")

    # Normalisation
    df = df[required].copy()
    df["User ID"] = df["User ID"].astype(str).str.strip().str.upper()
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce").dt.date
    df = df.dropna(subset=["Date"])

    return df


def compute_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """
    1) Compte des actions par (User ID, Application, Module)
    2) Pivot -> chaque user = ligne; colonnes = MultiIndex (Application, Module)
    3) Ratios par ligne (somme ≈ 1)
    """
    df_user_mod = (
        df.groupby(["User ID", "Application", "Module"])
          .size()
          .reset_index(name="Nb_actions")
    )

    df_module = df_user_mod.pivot_table(
        index="User ID",
        columns=["Application", "Module"],
        values="Nb_actions",
        fill_value=0
    )

    totals = df_module.sum(axis=1).replace(0, np.nan)
    df_profiles = df_module.div(totals, axis=0).fillna(0.0)
    df_profiles.index.name = "User ID"
    return df_profiles  # ratios ∈ [0,1]


def aggregate_by_application(df_profiles: pd.DataFrame) -> pd.DataFrame:
    """
    Agrège les ratios par Application (somme des modules d'une même application).
    Entrée: colonnes MultiIndex (Application, Module)
    Sortie: colonnes = Applications (str)
    """
    if isinstance(df_profiles.columns, pd.MultiIndex):
        agg = df_profiles.groupby(axis=1, level="Application").sum()
    else:
        # déjà agrégé
        agg = df_profiles.copy()
    agg.columns = agg.columns.astype(str)
    return agg


def auto_k_elbow(X, k_min: int = 1, k_max: int = 10):
    """
    Choisit K automatiquement par la méthode du coude (distorsion/inertia),
    et renvoie (k_auto, viz) où viz.fig est la figure Matplotlib à afficher.

    - Trace UNE SEULE courbe: inertie vs K
    - K est borné à [1..min(10, n_samples-1)] (pas de crash si peu d'utilisateurs)
    - Détection du coude = point le plus éloigné de la droite (k_min → k_max)
    """
    # Données
    X = np.asarray(X)
    n_samples = X.shape[0]
    if n_samples < 2:
        raise ValueError("Pas assez d'observations pour le clustering (n<2).")

    # Bornes robustes
    k_min = max(1, int(k_min))
    k_max = int(k_max)
    k_max = min(k_max, max(2, n_samples - 1))  # n_clusters <= n_samples-1

    if k_min > k_max:
        k_min = max(1, min(2, k_max))  # fallback
    Ks = list(range(k_min, k_max + 1))

    # Inerties
    inertias = []
    for k in Ks:
        km = KMeans(n_clusters=k, n_init="auto", random_state=42)
        km.fit(X)
        inertias.append(km.inertia_)

    # Détection du "coude" = point le plus éloigné de la droite (premier → dernier)
    x = np.array(Ks, dtype=float)
    y = np.array(inertias, dtype=float)
    # droite entre (x0,y0) et (x1,y1)
    x0, y0 = x[0], y[0]
    x1, y1 = x[-1], y[-1]
    # distance perpendiculaire de chaque point à la droite
    denom = np.hypot(x1 - x0, y1 - y0)
    if denom == 0:
        k_auto = Ks[0]
    else:
        distances = np.abs((y1 - y0) * x - (x1 - x0) * y + x1*y0 - y1*x0) / denom
        k_auto = int(x[np.argmax(distances)])

    # Figure compacte
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(Ks, inertias, marker="D")
    ax.axvline(k_auto, ls="--", color="k", alpha=0.6)
    ax.set_xlabel("K")
    ax.set_ylabel("Distorsion (inertia)")
    ax.set_title(f"Méthode du coude ({Ks[0]}–{Ks[-1]})")
    ax.grid(True, alpha=0.15)
    fig.tight_layout()

    # viz.fig pour rester compatible avec st.pyplot(viz.fig)
    viz = SimpleNamespace(fig=fig)
    return k_auto, viz


def cluster_with_k(ratios_df: pd.DataFrame, k: int) -> Tuple[pd.DataFrame, np.ndarray]:
    """
    KMeans(n_init='auto') sur ratios (Applications ou Modules).
    Retour:
      - df_clustered = ratios + colonne 'cluster'
      - labels = ndarray des labels
    """
    X = ratios_df.values
    km = KMeans(n_clusters=int(k), n_init="auto", random_state=42)
    labels = km.fit_predict(X)
    out = ratios_df.copy()
    out["cluster"] = labels
    return out, labels


def cluster_centers_mean(df_clustered: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule le profil moyen par cluster (moyenne des ratios).
    Retourne un DF index=cluster, colonnes = mêmes colonnes que df_clustered sans 'cluster'.
    """
    ratio_cols = [c for c in df_clustered.columns if c != "cluster"]
    centers = (
        df_clustered.groupby("cluster")[ratio_cols]
                    .mean()
                    .sort_index()
    )
    return centers


def modules_by_application(df_logs: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Retourne {Application: [modules uniques triés]} depuis le CSV brut.
    """
    m = (df_logs[["Application", "Module"]]
            .dropna()
            .drop_duplicates()
            .groupby("Application")["Module"]
            .apply(lambda s: sorted(s.unique().tolist()))
            .to_dict())
    return m

# --- Jours actifs distincts (TOTAL, sans double-compter par Application) ---
def user_active_days_total(df: pd.DataFrame) -> pd.Series:
    """
    Retourne une Series indexée par User ID avec le nb de jours DISTINCTS d'activité,
    en considérant un jour actif = présence d'au moins une ligne (peu importe l'application).
    """
    d = df.copy()
    d["User ID"] = d["User ID"].astype(str).str.strip().str.upper()
    d["Date"] = pd.to_datetime(d["Date"]).dt.date
    unique_days = d[["User ID", "Date"]].drop_duplicates()
    s = unique_days.groupby("User ID")["Date"].nunique().sort_values(ascending=False)
    s.name = "distinct_active_days"
    return s

def top_users_by_days(s_days: pd.Series, top_n: int = 10) -> pd.DataFrame:
    """Top N super users (jours actifs distincts)."""
    out = s_days.head(top_n).reset_index().rename(columns={"index": "User ID"})
    return out

def low_engagement_users(s_days: pd.Series, mode: str = "absolute", x: int = 3, q: float = 0.10) -> tuple[pd.DataFrame, int]:
    """
    Utilisateurs à faible engagement selon:
      - mode='absolute'  -> seuil = x jours (<= x)
      - mode='quantile'  -> seuil = quantile q (<= seuil_q)
    Retourne (df, seuil_utilisé).
    """
    if mode == "quantile":
        # q en [0,1] (ex: 0.10 pour 10%)
        thr = int(s_days.quantile(q))
    else:
        thr = int(x)

    mask = s_days <= thr
    out = s_days[mask].sort_values(ascending=True).reset_index().rename(columns={"index": "User ID"})
    return out, thr