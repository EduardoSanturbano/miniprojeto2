""""
Objetivo: gravar em data/raw/ os CSVs que as Etapas 2 e 3 vão consumir.

    mares_<ano>.csv      tábua de marés do ano (4 marés por dia)
    mares_previsao.csv   marés do mês corrente, para cruzar com a previsão
    ondas.csv            altura de onda hora a hora (~7 dias à frente)
    vento.csv            velocidade do vento hora a hora (~7 dias à frente)

Rodar com: uv run python src/scrape.py
"""

import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Os imports acima são o ponto de partida: você vai usar todos eles.
# Seu editor pode marcá-los como não usados até você preencher as funções.

URL_BASE = "https://tabuademares.com/br/paraiba/joao-pessoa"
URL_ONDAS = f"{URL_BASE}/previsao/ondas"
URL_VENTO = f"{URL_BASE}/previsao/vento"

# Servidores rejeitam clientes sem User-Agent. Identifique-se.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Segundos de pausa entre requests. Não tire isso.
PAUSA = 1.5

DIR_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def baixar_html(url: str, dados_post: dict | None = None) -> str:

    if dados_post is None:
        resp = requests.get(url, headers=HEADERS, timeout=20)
    else:
        resp = requests.post(url, data=dados_post, headers=HEADERS, timeout=20)

    resp.raise_for_status()

    return resp.text


def parsear_mares(html: str, ano: int, mes: int) -> list[dict]:

    soup = BeautifulSoup(html, "html.parser")
    mares = []

    tabela = soup.find("table", id="tabla_mareas")

    if tabela is None:
        raise ValueError("Tabela de marés não encontrada no HTML.")

    dias = tabela.find_all(
        "tr",
        class_="tabla_mareas_fila",
        onclick=True
    )

    for linha in dias:
        celulas = linha.find_all("td", recursive=False)

        if len(celulas) < 7:
            continue

        texto_dia = celulas[0].get_text(" ", strip=True)
        dia = int(texto_dia.split()[0])

        data = datetime(ano, mes, dia).strftime("%Y-%m-%d")

        texto_coeficiente = celulas[7].get_text(" ", strip=True) if len(celulas) > 7 else ""
        partes_coeficiente = texto_coeficiente.split()
        coeficiente = int(partes_coeficiente[0]) if partes_coeficiente and partes_coeficiente[0].isdigit() else None


        for celula in celulas[3:7]:
            partes = celula.get_text(" ", strip=True).split()

            if len(partes) < 2:
                continue

            hora = partes[0].zfill(5)
            altura = float(partes[1].replace(",", "."))

            classes = celula.get("class", [])
            tipo = None

            if "azul" in classes:
                tipo = "alta"
            elif "rojo" in classes:
                tipo = "baixa"
            else:
                if celula.select_one(".icon-ficha_pleamar"):
                    tipo = "alta"
                elif celula.select_one(".icon-ficha_bajamar"):
                    tipo = "baixa"

            mares.append({
                "data": data,
                "hora": hora,
                "altura": altura,
                "coeficiente": coeficiente,
                "tipo": tipo
            })

    return mares

def parsear_previsao(html: str, ano: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    previsoes = []

    meses = {
        "JAN": 1, "FEV": 2, "MAR": 3,
        "ABR": 4, "MAI": 5, "JUN": 6,
        "JUL": 7, "AGO": 8, "SET": 9,
        "OUT": 10, "NOV": 11, "DEZ": 12
    }

    fichas = soup.select(".fichas > .ficha")

    ano_atual = ano
    mes_anterior = None

    for ficha in fichas:
        dia = int(ficha.select_one(".f_circulo .dia").get_text(strip=True))
        mes_texto = ficha.select_one(".f_circulo .mes").get_text(strip=True).upper()
        mes = meses[mes_texto]

        if mes_anterior == 12 and mes == 1:
            ano_atual += 1

        data = datetime(ano_atual, mes, dia).strftime("%Y-%m-%d")
        mes_anterior = mes

        blocos_horarios = ficha.select(".f_temp_horas")

        for bloco in blocos_horarios:
            campos = bloco.select(".f_temp_hora")

            if len(campos) < 2:
                continue

            hora = campos[0].get_text(strip=True).zfill(5)
            direcao = campos[1].get_text(strip=True)

            elemento_ondas = bloco.select_one(
                ".tabla_mareas_marea_altura_numero"
            )

            elemento_vento = bloco.select_one(
                ".graf_color_velocidad"
            )

            if elemento_ondas is not None:
                valor = float(
                    elemento_ondas.get_text(strip=True).replace(",", ".")
                )
                unidade = "m"

            elif elemento_vento is not None:
                texto = elemento_vento.get_text(" ", strip=True)
                valor = float(
                    texto.replace("km/h", "").replace(",", ".").strip()
                )
                unidade = "km/h"

            else:
                continue

            previsoes.append({
                "data": data,
                "hora": hora,
                "direcao": direcao,
                "valor": valor,
                "unidade": unidade
            })

    return previsoes


def coletar_mares_do_ano(ano: int) -> pd.DataFrame:
    todas_mares = []

    for mes in range(1, 13):
        data_consulta = f"{ano}-{mes:02d}-01"

        dados = {
            "fecha": data_consulta
        }

        html = baixar_html(URL_BASE, dados_post=dados)

        mares_mes = parsear_mares(html, ano, mes)

        todas_mares.extend(mares_mes)

        print(f"Mês {mes:02d}/{ano}: {len(mares_mes)} marés coletadas")

        if mes < 12:
            time.sleep(PAUSA)

    return pd.DataFrame(todas_mares)


def main(ano: int = 2025) -> None:
    DIR_RAW.mkdir(parents=True, exist_ok=True)
    hoje = datetime.now()

    df_mares = coletar_mares_do_ano(ano)

    caminho = DIR_RAW / f"mares_{ano}.csv"
    df_mares.to_csv(caminho, index=False)

    print(f"{caminho.name}: {len(df_mares)} linhas")

    time.sleep(PAUSA)

    dados = {
        "fecha": hoje.strftime("%Y-%m-01")
    }

    html = baixar_html(URL_BASE, dados_post=dados)

    mares_previsao = parsear_mares(
        html, hoje.year, hoje.month
    )

    df_mares_previsao = pd.DataFrame(mares_previsao)

    caminho = DIR_RAW / "mares_previsao.csv"
    df_mares_previsao.to_csv(caminho, index=False)

    print(f"{caminho.name}: {len(df_mares_previsao)} linhas")

    time.sleep(PAUSA)


    html = baixar_html(URL_ONDAS)
    ondas = parsear_previsao(html, hoje.year)

    df_ondas = pd.DataFrame(ondas)

    caminho = DIR_RAW / "ondas.csv"
    df_ondas.to_csv(caminho, index=False)

    print(f"{caminho.name}: {len(df_ondas)} linhas")

    time.sleep(PAUSA)

    html = baixar_html(URL_VENTO)
    vento = parsear_previsao(html, hoje.year)

    df_vento = pd.DataFrame(vento)

    caminho = DIR_RAW / "vento.csv"
    df_vento.to_csv(caminho, index=False)

    print(f"{caminho.name}: {len(df_vento)} linhas")
    
if __name__ == "__main__":
    main()