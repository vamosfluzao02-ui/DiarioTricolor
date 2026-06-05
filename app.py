import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
import re
import random
from bs4 import BeautifulSoup
from collections import Counter
import time
from datetime import datetime, timedelta

# ======================================================
# CONFIG
# ======================================================

ACCESS_TOKEN = "EAAYDRMk29tUBRulDdppK5QBaM9bpXgFbpsMpBvObc54tGg0ZA5FZCkOqW9BjsOCJV6c8N9sdOplIsPHebaZB4AUWYyxcldpG4Sm76NZAtgmZAyZAnsM0ZB3ZCHHKZCU63XOpiKEwZCK2MmiMDw7bPQRxPPaWZB5Se7WmOd3zCqZC9BU3eehS9RhJezljezw30Q63vtJkwe7JhqTBMKF1ZABM0"
IG_USER_ID = "17841466855594663"

st.set_page_config(
    page_title="Diário Tricolor",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
<style>
[data-testid="stMetric"] {
    background-color: white;
    border-radius: 15px;
    padding: 20px;
    box-shadow: 0px 4px 15px rgba(0,0,0,0.10);
}

/* Número principal — grená fixo em dark e light mode */
[data-testid="stMetricValue"] > div {
    color: #7A1531 !important;
    font-weight: 700 !important;
}

/* Label acima do número */
[data-testid="stMetricLabel"] > div > p {
    color: #7A1531 !important;
    font-weight: 600 !important;
}

/* Delta (variação ↑↓) */
[data-testid="stMetricDelta"] > div {
    color: #0E7A32 !important;
    font-weight: 600 !important;
}

.main { background-color: #f4f6f8; }
h1 { color: #7A1531; }
h2, h3 { color: #0E7A32; }
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0E7A32 0%, #7A1531 100%);
}
</style>
""", unsafe_allow_html=True)

# ======================================================
# FUNÇÕES DE DADOS
# ======================================================

@st.cache_data(ttl=300)
def carregar_perfil():
    try:
        url = (
            f"https://graph.facebook.com/v19.0/{IG_USER_ID}"
            f"?fields=name,username,biography,followers_count,"
            f"follows_count,media_count"
            f"&access_token={ACCESS_TOKEN}"
        )
        response = requests.get(url)
        return response.json()
    except Exception as e:
        st.error(f"Erro ao carregar perfil: {e}")
        return {}

@st.cache_data(ttl=300)
def carregar_posts():
    try:
        url = (
            f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
            f"?fields=id,caption,media_type,media_url,thumbnail_url,timestamp,like_count,comments_count,permalink"
            f"&limit=50"
            f"&access_token={ACCESS_TOKEN}"
        )
        response = requests.get(url)
        dados = response.json()

        if "data" not in dados:
            st.error("API não retornou dados dos posts.")
            st.write(dados)
            return pd.DataFrame()

        df = pd.DataFrame(dados["data"])

        if df.empty:
            return pd.DataFrame()

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["Data"] = df["timestamp"].dt.date
        else:
            df["Data"] = None

        if "media_type" in df.columns:
            df["Formato"] = df["media_type"].replace({
                "IMAGE": "Foto",
                "VIDEO": "Vídeo/Reels",
                "CAROUSEL_ALBUM": "Carrossel"
            })
        else:
            df["Formato"] = "Desconhecido"

        return df
    except Exception as e:
        st.error(f"Erro ao carregar posts: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def carregar_historico_seguidores():
    """
    Busca histórico diário de seguidores via Instagram Insights API.
    'follower_count' retorna GANHOS diários (não total acumulado).
    Retorna (DataFrame, erro_str|None).
    """
    try:
        since = int((datetime.now() - timedelta(days=90)).timestamp())
        until = int(datetime.now().timestamp())
        url = (
            f"https://graph.facebook.com/v19.0/{IG_USER_ID}/insights"
            f"?metric=follower_count"
            f"&period=day"
            f"&since={since}"
            f"&until={until}"
            f"&access_token={ACCESS_TOKEN}"
        )
        response = requests.get(url, timeout=10)
        dados = response.json()

        if "error" in dados:
            return pd.DataFrame(), dados["error"].get("message", "Erro da API")

        if "data" not in dados or not dados["data"]:
            return pd.DataFrame(), "API retornou vazio"

        valores = dados["data"][0].get("values", [])
        if not valores:
            return pd.DataFrame(), "Nenhum valor retornado"

        df = pd.DataFrame(valores)
        df = df.rename(columns={"value": "Seguidores", "end_time": "Data"})
        df["Data"] = pd.to_datetime(df["Data"], utc=True).dt.tz_convert("America/Sao_Paulo").dt.normalize()
        df["Data"] = df["Data"].dt.tz_localize(None)
        df = df.sort_values("Data").reset_index(drop=True)
        return df, None

    except Exception as e:
        return pd.DataFrame(), str(e)

@st.cache_data(ttl=300)
def noticias_ge_fluminense():
    url = "https://ge.globo.com/futebol/times/fluminense/"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        noticias = []
        for item in soup.find_all("a"):
            texto = item.get_text().strip()
            link = item.get("href")
            if texto and len(texto) > 30 and "fluminense" in texto.lower():
                noticias.append({"titulo": texto, "link": link})
        return pd.DataFrame(noticias).drop_duplicates().head(15)
    except Exception as e:
        st.error(f"Erro ao buscar notícias: {e}")
        return pd.DataFrame()

# ======================================================
# CARREGAMENTO DOS DADOS
# ======================================================

perfil = carregar_perfil()
posts = carregar_posts()

if not posts.empty:
    if "Data" in posts.columns:
        posts["Data"] = pd.to_datetime(posts["Data"])

    if "like_count" in posts.columns and "comments_count" in posts.columns:
        posts["Engajamento"] = (
            posts["like_count"].fillna(0) + posts["comments_count"].fillna(0)
        )

    dias_map = {
        "Monday": "Segunda", "Tuesday": "Terça", "Wednesday": "Quarta",
        "Thursday": "Quinta", "Friday": "Sexta",
        "Saturday": "Sábado", "Sunday": "Domingo"
    }
    posts["DiaSemana"] = posts["Data"].dt.day_name().replace(dias_map)

# ======================================================
# SIDEBAR
# ======================================================

st.sidebar.title("📊 Diário Tricolor")

periodo = st.sidebar.selectbox("📅 Período", [7, 30, 90, 365])

if not posts.empty:
    limite = datetime.now() - timedelta(days=periodo)
    posts = posts[posts["Data"] >= limite]

if not posts.empty:
    csv = posts.to_csv(index=False).encode("utf-8")
    st.sidebar.download_button("📥 Exportar CSV", csv, "diario_tricolor.csv", "text/csv")

# ======================================================
# TABS PRINCIPAIS
# ======================================================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📈 Insights",
    "📰 Notícias (GE)",
    "🔥 Editor IA",
    "🚨 Breaking & Rumores",
    "🤖 GE Bot Live",
    "📊 Crescimento"
])

# ======================================================
# TAB 1 — INSIGHTS
# ======================================================

with tab1:
    st.title("📈 Diário Tricolor — Insights")

    seguidores = perfil.get("followers_count", 0)
    total_posts = perfil.get("media_count", 0)
    likes_total = int(posts["like_count"].sum()) if "like_count" in posts.columns else 0
    comentarios_total = int(posts["comments_count"].sum()) if "comments_count" in posts.columns else 0
    media_likes = round(posts["like_count"].mean()) if "like_count" in posts.columns else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("👥 Seguidores", f"{seguidores:,}".replace(",", "."))
    c2.metric("📸 Posts", total_posts)
    c3.metric("❤️ Likes", f"{likes_total:,}".replace(",", "."))
    c4.metric("💬 Comentários", f"{comentarios_total:,}".replace(",", "."))
    c5.metric("🔥 Média Likes", media_likes)

    st.divider()

    if not posts.empty and "Data" in posts.columns:
        col1, col2 = st.columns(2)

        if "like_count" in posts.columns:
            likes_dia = posts.groupby("Data")["like_count"].sum().reset_index()
            fig_likes = px.line(likes_dia, x="Data", y="like_count", title="Likes por Dia", markers=True)
            col1.plotly_chart(fig_likes, use_container_width=True)

        if "comments_count" in posts.columns:
            comentarios_dia = posts.groupby("Data")["comments_count"].sum().reset_index()
            fig_coment = px.line(comentarios_dia, x="Data", y="comments_count", title="Comentários por Dia", markers=True)
            col2.plotly_chart(fig_coment, use_container_width=True)

    st.divider()

    if not posts.empty and "Engajamento" in posts.columns:
        engajamento_dia = posts.groupby("Data")["Engajamento"].sum().reset_index()
        fig_eng = px.area(engajamento_dia, x="Data", y="Engajamento", title="📈 Evolução do Engajamento")
        st.plotly_chart(fig_eng, use_container_width=True)

        if perfil.get("followers_count", 0) > 0:
            taxa = round(posts["Engajamento"].sum() / perfil["followers_count"] * 100, 2)
            fig_taxa = px.pie(values=[taxa, 100 - taxa], names=["Engajamento", "Restante"], title="Taxa de Engajamento")
            st.plotly_chart(fig_taxa)

    col3, col4 = st.columns(2)

    if "Formato" in posts.columns:
        formatos = posts["Formato"].value_counts().reset_index()
        formatos.columns = ["Formato", "Quantidade"]
        fig_formato = px.pie(formatos, names="Formato", values="Quantidade", title="Distribuição dos Conteúdos")
        col3.plotly_chart(fig_formato, use_container_width=True)

    if not posts.empty and "like_count" in posts.columns:
        top5 = posts.sort_values("like_count", ascending=False).head(5)
        col4.subheader("🏆 Top 5 Posts")
        col4.dataframe(top5[["Data", "like_count", "comments_count", "caption"]].rename(
            columns={"like_count": "Likes", "comments_count": "Comentários", "caption": "Legenda"}
        ), use_container_width=True)

    st.divider()
    st.subheader("🏆 Melhores Posts")

    if not posts.empty and "Engajamento" in posts.columns:
        top_posts = posts.sort_values("Engajamento", ascending=False).head(5)

        for _, post in top_posts.iterrows():
            col1, col2 = st.columns([1, 3])
            with col1:
                if "media_url" in post and pd.notna(post.get("media_url")):
                    st.image(post["media_url"], width=180)
            with col2:
                st.metric("Engajamento", int(post["Engajamento"]))
                st.write(f"❤️ {int(post['like_count'])}   💬 {int(post['comments_count'])}")
                if "caption" in post and pd.notna(post.get("caption")):
                    st.write(post["caption"][:150])

        st.divider()
        st.subheader("📋 Análise de Conteúdo")

        if "like_count" in posts.columns:
            top_likes = posts.sort_values("like_count", ascending=False)
            fig_top = px.bar(
                top_likes.head(10), x="like_count", y="Formato",
                orientation="h", title="Top 10 Posts por Likes"
            )
            st.plotly_chart(fig_top, use_container_width=True)

        st.subheader("📋 Ranking Completo")
        st.dataframe(posts, use_container_width=True)

        st.divider()
        st.subheader("📌 Insights Automáticos")

        media_geral = posts["Engajamento"].mean()
        ultimo_post = posts.iloc[0]
        diferenca = ((ultimo_post["Engajamento"] - media_geral) / media_geral) * 100

        if diferenca > 0:
            st.success(f"Último post performou {diferenca:.1f}% acima da média.")
        else:
            st.warning(f"Último post ficou {abs(diferenca):.1f}% abaixo da média.")

        formato = posts.groupby("Formato")["Engajamento"].mean().sort_values(ascending=False)
        melhor_formato = formato.index[0]
        st.info(f"🏆 Melhor formato: {melhor_formato}")

        melhor_dia = posts.groupby("DiaSemana")["Engajamento"].mean().sort_values(ascending=False)
        st.info(f"📅 Melhor dia: {melhor_dia.index[0]}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏆 Melhor Formato", melhor_formato)
        c2.metric("📅 Melhor Dia", melhor_dia.index[0])
        c3.metric("🔥 Média Engajamento", round(media_geral))
        c4.metric("📈 Melhor Post", int(posts["Engajamento"].max()))

        st.divider()
        reels = posts[posts["Formato"] == "Vídeo/Reels"]

        if not reels.empty:
            melhor_reel = reels.loc[reels["Engajamento"].idxmax()]
            st.subheader("🎬 Melhor Reel")
            c1, c2 = st.columns([1, 2])
            with c1:
                if "media_url" in melhor_reel and pd.notna(melhor_reel.get("media_url")):
                    st.image(melhor_reel["media_url"], use_container_width=True)
            with c2:
                st.metric("🔥 Engajamento", int(melhor_reel["Engajamento"]))
                st.metric("❤️ Likes", int(melhor_reel["like_count"]))
                st.metric("💬 Comentários", int(melhor_reel["comments_count"]))
                st.write(f"📅 {melhor_reel['Data'].strftime('%d/%m/%Y')}")
                if "caption" in melhor_reel and pd.notna(melhor_reel.get("caption")):
                    st.write(melhor_reel["caption"][:250])

            st.subheader("🎬 Top 10 Reels")
            top_reels = reels.sort_values("Engajamento", ascending=False).head(10)
            for i, (_, reel) in enumerate(top_reels.iterrows(), start=1):
                with st.container():
                    col1, col2 = st.columns([1, 3])
                    with col1:
                        if pd.notna(reel.get("media_url")):
                            st.image(reel["media_url"], width=180)
                    with col2:
                        st.markdown(f"### #{i}")
                        st.write(f"🔥 Engajamento: {int(reel['Engajamento'])}")
                        st.write(f"❤️ Likes: {int(reel['like_count'])}")
                        st.write(f"💬 Comentários: {int(reel['comments_count'])}")
                        st.write(f"📅 {reel['Data'].strftime('%d/%m/%Y')}")
                        if "caption" in reel and pd.notna(reel.get("caption")):
                            st.write(reel["caption"][:120] + "...")
                    st.divider()

# ======================================================
# TAB 2 — NOTÍCIAS (GE)
# ======================================================

with tab2:
    st.title("📰 Notícias do Fluminense — GE")

    df_news = noticias_ge_fluminense()

    if not df_news.empty:
        st.subheader("📰 Últimas Notícias")
        st.dataframe(df_news, use_container_width=True)

        st.subheader("🔥 GE Bot Real Time")
        def score_ge(titulo):
            t = titulo.lower()
            score = 0
            for p in ["mercado", "contrato", "lesão", "renovação", "saída", "reforço", "fluminense", "negociação"]:
                if p in t:
                    score += 10
            return score

        df_bot = df_news.copy()
        df_bot["score"] = df_bot["titulo"].apply(score_ge)
        st.dataframe(df_bot.sort_values("score", ascending=False).head(10), use_container_width=True)

        st.subheader("🧠 Editor GE Automático")
        def editor_ge(df):
            df = df.copy()
            def process(row):
                titulo = row["titulo"]
                resumo = ". ".join(titulo.split(".")[:2]).strip()
                return pd.Series([
                    f"Fluminense: {titulo}",
                    resumo,
                    f"🟢 Fluminense | {resumo}",
                    f"⚽ Fluminense: {resumo} #Fluminense #Futebol"
                ])
            df[["Manchete", "Resumo", "Instagram", "Twitter"]] = df.apply(process, axis=1)
            return df
        st.dataframe(editor_ge(df_news), use_container_width=True)

        st.subheader("🧠 Editor Chefe IA — Notícia do Dia")
        def score_noticia(titulo):
            t = str(titulo).lower()
            score = 0
            for p in ["mercado", "contratação", "proposta", "negociação", "lesão", "saída", "renovação", "crise", "decisão", "oficial", "confirmado", "acordo"]:
                if p in t: score += 15
            for j in ["cano", "ganso", "fábio", "keno", "martinelli", "john kennedy", "soteldo"]:
                if j in t: score += 20
            if len(t) > 80: score += 5
            if any(x in t for x in ["urgente", "oficial", "agora"]): score += 10
            return score

        df_score = df_news.copy()
        df_score = df_score[df_score["titulo"].notna()]
        df_score["score"] = df_score["titulo"].apply(score_noticia)
        top = df_score.sort_values("score", ascending=False).head(1)
        if not top.empty:
            escolhida = top.iloc[0]
            st.success("🏆 NOTÍCIA ESCOLHIDA DO DIA")
            st.write("📰", escolhida["titulo"])
            st.metric("🔥 Score Editorial", int(escolhida["score"]))
            st.info(f"""
🧠 DECISÃO DO EDITOR CHEFE

📌 Notícia escolhida:
{escolhida['titulo']}

🔥 Motivo:
- Alto potencial de engajamento
- Presença de termos relevantes para o Fluminense
- Forte impacto editorial
- Potencial de repercussão em redes sociais

📊 Score editorial: {escolhida['score']:.0f}
""")

        st.subheader("🎯 Radar de Mercado")
        def radar_mercado(df):
            texto = " ".join(df["titulo"].astype(str)).lower()
            jogadores = ["cano", "ganso", "keno", "fábio", "martinelli", "john kennedy", "soteldo", "guga", "renê"]
            ranking = [{"Jogador": j.title(), "Menções": texto.count(j)} for j in jogadores if texto.count(j) > 0]
            if not ranking:
                return pd.DataFrame({"Jogador": [], "Menções": []})
            return pd.DataFrame(ranking).sort_values("Menções", ascending=False)
        radar = radar_mercado(df_news)
        if not radar.empty:
            st.dataframe(radar, use_container_width=True)
        else:
            st.info("Nenhum jogador mencionado nas notícias recentes.")
    else:
        st.warning("Nenhuma notícia encontrada no momento.")

# ======================================================
# TAB 3 — EDITOR IA
# ======================================================

with tab3:
    st.title("🔥 Editor IA — Análise de Notícia")

    if not posts.empty and "Engajamento" in posts.columns:

        def importancia_jogador(nome, posts_df):
            df = posts_df[posts_df["caption"].str.contains(nome, case=False, na=False)]
            if df.empty:
                return posts_df["Engajamento"].mean() * 0.5
            return df["Engajamento"].mean()

        def peso_jogador(nome, posts_df):
            score = importancia_jogador(nome, posts_df)
            media = posts_df["Engajamento"].mean()
            return min(score / media, 2) * 15

        def score_noticia_ge(texto, posts_df):
            texto = texto.lower()
            score = 50
            jogadores = list(set(re.findall(r"[a-zçãõéíóú]{3,}", texto)))
            for j in jogadores:
                score += peso_jogador(j, posts_df)
            for p in ["mercado", "proposta", "interesse", "negociação", "bastidores", "renovação", "decisão", "sondagem", "contrato", "assina", "saída"]:
                if p in texto: score += 4
            if len(texto) > 120: score += 5
            if len(texto.split()) > 20: score += 5
            for p in ["crise", "choque", "absurdo", "urgente", "bombástico"]:
                if p in texto: score -= 8
            if "." in texto: score += 3
            return round(max(0, min(score, 100)), 2)

        def categoria(score):
            if score >= 80: return "🟢 GE PREMIUM (Alta repercussão)"
            elif score >= 60: return "🟡 Boa para Lance / ESPN"
            elif score >= 40: return "🟠 Conteúdo leve para redes sociais"
            else: return "🔴 Baixo potencial editorial"

        noticia = st.text_area(
            "✍️ Escreva sua notícia sobre o Fluminense",
            placeholder="Ex: Fluminense avalia futuro de Cano com contrato até 2026..."
        )

        if noticia and noticia.strip():
            score = score_noticia_ge(noticia, posts)
            st.metric("📊 Score Editorial", score)
            st.info(categoria(score))

            st.subheader("🧠 Por que esse score?")
            if "mercado" in noticia.lower():
                st.write("📈 Tema forte de mercado da bola")
            if len(noticia) > 120:
                st.write("📰 Texto com profundidade editorial")
            if any(x in noticia.lower() for x in ["crise", "choque", "absurdo"]):
                st.write("⚠️ Tom sensacionalista detectado")

            st.subheader("⚽ Jogadores detectados na notícia")
            encontrados = [
                j for j in set(posts["caption"].dropna().astype(str).str.cat(sep=" ").split())
                if j.lower() in noticia.lower()
            ]
            st.write(encontrados if encontrados else "Nenhum jogador relevante detectado")

        st.divider()
        st.subheader("🧠 Previsão de Viralização")

        def prever_viral(texto, posts_df):
            texto = texto.lower()
            score = 50
            for p in ["mercado", "proposta", "negociação", "interesse", "saída", "renovação", "bastidores", "decisão", "crise", "titular", "lesão"]:
                if p in texto: score += 5
            for nome in posts_df["caption"].dropna().astype(str):
                if nome.lower() in texto:
                    score += posts_df["Engajamento"].mean() / 50
            if 80 <= len(texto) <= 200: score += 10
            if any(x in texto for x in ["urgente", "bombástico", "choque"]): score -= 10
            return min(max(score, 0), 100)

        texto_viral = st.text_area("✍️ Escreva sua notícia (Previsão Viral)", key="viral")
        if texto_viral:
            viral = prever_viral(texto_viral, posts)
            st.metric("🔥 Chance de viralizar", f"{viral:.0f}%")
            if viral >= 75: st.success("🚀 Alta chance de viralização")
            elif viral >= 50: st.warning("⚠️ Médio potencial")
            else: st.error("📉 Baixo alcance esperado")

            templates = [
                f"Fluminense avalia cenário envolvendo {texto_viral}",
                f"Bastidores do Fluminense: {texto_viral}",
                f"Decisão no Fluminense pode impactar temporada: {texto_viral}",
                f"Mercado da bola: Fluminense e o futuro de {texto_viral}",
                f"Fluminense toma decisão importante sobre {texto_viral}"
            ]
            st.subheader("📰 Manchete Automática")
            st.info(random.choice(templates))

    else:
        st.warning("Carregue os dados do Instagram para usar o Editor IA.")

# ======================================================
# TAB 4 — BREAKING & RUMORES
# ======================================================

with tab4:
    st.title("🚨 Breaking News & Rumores")

    if not posts.empty:
        st.subheader("🚨 Breaking Detector (Posts Instagram)")
        palavras_breaking = ["urgente", "agora", "confirmado", "oficial", "última hora", "acabou de"]

        def check_breaking(texto):
            texto = str(texto).lower()
            return any(p in texto for p in palavras_breaking)

        df_breaking = posts.copy()
        df_breaking["breaking"] = df_breaking["caption"].apply(check_breaking)
        bd = df_breaking[df_breaking["breaking"]].head(5)

        if bd.empty:
            st.success("🟢 Nenhum breaking news no momento")
        else:
            st.error("🚨 BREAKING NEWS DETECTADO")
            st.dataframe(bd[["Data", "caption", "like_count", "comments_count"]], use_container_width=True)

        st.divider()
        st.subheader("🔥 Detector de Breaking News (Texto Livre)")

        def detectar_breaking(texto):
            texto = texto.lower()
            sinais = sum(1 for p in ["agora", "urgente", "confirmado", "oficial", "acabou de", "última hora"] if p in texto)
            sinais += sum(1 for j in ["cano", "ganso", "fábio", "keno", "martinelli"] if j in texto)
            return sinais >= 2

        texto_break = st.text_area("✍️ Cole um texto para análise", key="breaking")
        if texto_break:
            if detectar_breaking(texto_break):
                st.error("🚨 BREAKING NEWS DETECTADO")
            else:
                st.info("🟢 Conteúdo normal")

        st.divider()
        st.subheader("🧠 Alerta de Rumor (Posts Instagram)")

        def alerta_rumor(posts_df, jogador):
            df = posts_df[posts_df["caption"].str.contains(jogador, case=False, na=False)]
            if df.empty:
                return f"🔴 Nenhum post recente menciona {jogador}"
            return f"🚨 {len(df)} post(s) mencionam {jogador}! Possível movimentação."

        jogador_ig = st.text_input("🔍 Buscar jogador (Posts Instagram)", key="rumor_ig")
        if jogador_ig:
            st.warning(alerta_rumor(posts, jogador_ig))

    df_news_tab4 = noticias_ge_fluminense()
    if not df_news_tab4.empty:
        st.divider()
        st.subheader("🧠 Alerta de Rumor (GE)")

        def alerta_rumor_ge(jogador, df):
            df_filtrado = df[df["titulo"].str.contains(jogador, case=False, na=False)]
            if df_filtrado.empty:
                return f"🔴 Nenhuma notícia recente sobre {jogador} no GE"
            return f"🚨 GE NOTICIOU movimentação sobre {jogador}!"

        jogador_ge = st.text_input("🔍 Buscar jogador (GE)", key="rumor_ge")
        if jogador_ge:
            st.warning(alerta_rumor_ge(jogador_ge, df_news_tab4))

# ======================================================
# TAB 5 — GE BOT LIVE
# ======================================================

with tab5:
    st.title("🤖 GE Bot Live")

    st.subheader("📈 Trend Shift (Fluminense)")

    if not posts.empty and "Engajamento" in posts.columns:
        df_ts = posts.copy().sort_values("Data")
        recentes = df_ts.tail(10)
        antigos = df_ts.head(10)
        crescimento = recentes["Engajamento"].mean() - antigos["Engajamento"].mean()
        st.metric("Variação de tendência", round(crescimento))
        st.info("📈 Subindo forte" if crescimento > 0 else "📉 Caindo")

        st.divider()
        st.subheader("🏆 Ranking Editorial dos Posts")

        def ranking_noticias(posts_df):
            df = posts_df.copy()
            df["score"] = df["Engajamento"] * 0.7 + df["like_count"] * 0.2 + df["comments_count"] * 0.1
            return df.sort_values("score", ascending=False)[["caption", "score"]].head(10)

        st.dataframe(ranking_noticias(posts), use_container_width=True)

        st.divider()
        st.subheader("🧠 Score de Tendência por Caption")

        def score_tendencia(texto):
            texto = str(texto).lower()
            score = 0
            for p in ["mercado", "proposta", "negociação", "interesse", "contrato", "renovação", "saída", "bastidores", "urgente", "confirmado", "oficial"]:
                if p in texto: score += 3
            for j in ["cano", "ganso", "keno", "fábio", "martinelli", "john kennedy"]:
                if j in texto: score += 5
            if len(texto) > 120: score += 2
            return score

        df_ge = posts.copy()
        df_ge["trend_score"] = df_ge["caption"].fillna("").apply(score_tendencia)
        df_ge = df_ge.sort_values("trend_score", ascending=False)
        st.dataframe(df_ge[["caption", "trend_score", "like_count", "comments_count"]].head(10), use_container_width=True)
    else:
        st.warning("Nenhum dado disponível para análise de tendências.")

    st.divider()
    st.subheader("📰 GE News em Tempo Real")
    df_ge_live = noticias_ge_fluminense()
    if not df_ge_live.empty:
        st.dataframe(df_ge_live, use_container_width=True)
    else:
        st.warning("Sem notícias no momento.")

# ======================================================
# TAB 6 — CRESCIMENTO
# ======================================================

with tab6:
    st.title("📊 Crescimento da Conta")

    seguidores_atual = perfil.get("followers_count", 0)
    seguindo_atual = perfil.get("follows_count", 0)
    total_posts_perfil = perfil.get("media_count", 0)

    # ── Métricas de cabeçalho ──────────────────────────
    c1, c2, c3 = st.columns(3)
    c1.metric("👥 Seguidores Hoje", f"{seguidores_atual:,}".replace(",", "."))
    c2.metric("➡️ Seguindo", f"{seguindo_atual:,}".replace(",", "."))
    c3.metric("📸 Total de Posts", total_posts_perfil)

    st.divider()

    # ── SEÇÃO 1: Seguidores históricos via Insights API ──
    st.subheader("📈 Evolução de Seguidores")

    hist_seg, erro_seg = carregar_historico_seguidores()

    if erro_seg:
        st.error(f"❌ Erro ao buscar histórico de seguidores: {erro_seg}")

    elif hist_seg.empty:
        st.warning("A API não retornou dados de seguidores. Verifique se a permissão instagram_manage_insights está ativa no token.")

    else:
        # Reconstruir curva acumulada: ganhos diários -> total ao longo do tempo
        ganhos = hist_seg["Seguidores"].values
        total_inicio = seguidores_atual - int(ganhos.sum())
        acumulado = [int(total_inicio + ganhos[:i+1].sum()) for i in range(len(ganhos))]
        hist_seg = hist_seg.copy()
        hist_seg["Total"] = acumulado

        # Variações para delta nos cards
        ganho_7d  = int(hist_seg.tail(7)["Seguidores"].sum())
        ganho_30d = int(hist_seg.tail(30)["Seguidores"].sum())
        media_dia = round(float(hist_seg["Seguidores"].mean()), 1)
        melhor_dia_seg = hist_seg.loc[hist_seg["Seguidores"].idxmax()]

        # Cards de resumo
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📅 Ganho últimos 7 dias",  f"+{ganho_7d:,}".replace(",", "."))
        c2.metric("📅 Ganho últimos 30 dias", f"+{ganho_30d:,}".replace(",", "."))
        c3.metric("📊 Média diária",           f"+{media_dia}")
        c4.metric("🏆 Melhor dia",             melhor_dia_seg["Data"].strftime("%d/%m"),
                  delta=f"+{int(melhor_dia_seg['Seguidores'])} nesse dia")

        # Gráfico de linha — curva acumulada
        fig_seg = px.line(
            hist_seg, x="Data", y="Total",
            title="📈 Total de seguidores ao longo do tempo (últimos 90 dias)",
            markers=True,
            labels={"Total": "Seguidores", "Data": "Data"},
            color_discrete_sequence=["#0E7A32"]
        )
        fig_seg.update_traces(fill="tozeroy", fillcolor="rgba(14,122,50,0.08)")
        fig_seg.update_layout(hovermode="x unified")
        st.plotly_chart(fig_seg, use_container_width=True)

        # Gráfico de barras — ganho diário
        fig_ganho = px.bar(
            hist_seg, x="Data", y="Seguidores",
            title="🟢 Novos seguidores por dia",
            labels={"Seguidores": "Novos seguidores"},
            color="Seguidores",
            color_continuous_scale=["#c8e6c9", "#0E7A32"]
        )
        fig_ganho.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig_ganho, use_container_width=True)

        # Média móvel 7 dias
        hist_seg["Media7d"] = hist_seg["Seguidores"].rolling(7, min_periods=1).mean()
        fig_mm = px.line(
            hist_seg, x="Data", y="Media7d",
            title="📊 Média móvel (7 dias) — ritmo de crescimento",
            labels={"Media7d": "Média móvel (seguidores/dia)"},
            color_discrete_sequence=["#7A1531"]
        )
        st.plotly_chart(fig_mm, use_container_width=True)

        # Tabela detalhada expansível
        with st.expander("📋 Ver tabela completa de seguidores por dia"):
            st.dataframe(
                hist_seg[["Data", "Seguidores", "Total"]].rename(
                    columns={"Seguidores": "Novos no dia", "Total": "Total acumulado"}
                ).sort_values("Data", ascending=False),
                use_container_width=True
            )

    st.divider()

    # ── SEÇÃO 2: Posts por dia ──────────────────────────
    st.subheader("📸 Posts Publicados por Dia")

    if not posts.empty and "Data" in posts.columns:
        posts_por_dia = posts.groupby("Data").size().reset_index(name="Posts")
        posts_por_dia = posts_por_dia.sort_values("Data")

        fig_posts_dia = px.bar(
            posts_por_dia, x="Data", y="Posts",
            title="📸 Quantidade de posts por dia",
            color="Posts",
            color_continuous_scale=["#e8f5e9", "#0E7A32"],
            labels={"Posts": "Nº de Posts"}
        )
        fig_posts_dia.update_layout(showlegend=False)
        st.plotly_chart(fig_posts_dia, use_container_width=True)

        # Posts por dia da semana
        if "DiaSemana" in posts.columns:
            ordem_dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
            posts_semana = posts.groupby("DiaSemana").size().reset_index(name="Posts")
            posts_semana["DiaSemana"] = pd.Categorical(posts_semana["DiaSemana"], categories=ordem_dias, ordered=True)
            posts_semana = posts_semana.sort_values("DiaSemana")

            fig_semana = px.bar(
                posts_semana, x="DiaSemana", y="Posts",
                title="📅 Posts por dia da semana",
                color="Posts",
                color_continuous_scale=["#e8f5e9", "#7A1531"],
            )
            st.plotly_chart(fig_semana, use_container_width=True)

        # Posts por formato ao longo do tempo
        if "Formato" in posts.columns:
            posts_formato_dia = posts.groupby(["Data", "Formato"]).size().reset_index(name="Posts")
            fig_formato_linha = px.line(
                posts_formato_dia, x="Data", y="Posts", color="Formato",
                title="📊 Frequência de publicação por formato",
                markers=True
            )
            st.plotly_chart(fig_formato_linha, use_container_width=True)

        # Métricas de frequência
        st.divider()
        total_dias = (posts["Data"].max() - posts["Data"].min()).days + 1
        media_posts_dia = round(len(posts) / max(total_dias, 1), 2)
        dia_mais_ativo = posts_por_dia.loc[posts_por_dia["Posts"].idxmax()]
        mes_mais_ativo = posts.groupby(posts["Data"].dt.to_period("M")).size().idxmax()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📊 Média posts/dia", media_posts_dia)
        c2.metric("🏆 Dia mais ativo", dia_mais_ativo["Data"].strftime("%d/%m"))
        c3.metric("📅 Posts nesse dia", int(dia_mais_ativo["Posts"]))
        c4.metric("🗓️ Mês mais ativo", str(mes_mais_ativo))

        # Tabela resumo por mês
        st.subheader("🗓️ Resumo mensal de publicações")
        posts_mes = posts.copy()
        posts_mes["Mês"] = posts_mes["Data"].dt.to_period("M").astype(str)
        resumo_mes = posts_mes.groupby("Mês").agg(
            Posts=("id", "count"),
            Likes=("like_count", "sum"),
            Comentarios=("comments_count", "sum")
        ).reset_index()
        resumo_mes["Engajamento Total"] = resumo_mes["Likes"] + resumo_mes["Comentarios"]
        st.dataframe(resumo_mes.sort_values("Mês", ascending=False), use_container_width=True)

    else:
        st.warning("Sem dados de posts disponíveis para exibir.")
