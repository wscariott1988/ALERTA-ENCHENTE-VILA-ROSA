import requests
import time
import json
import os
import threading
import http.server
import socketserver

# ================= CONFIGURAÇÕES =================
TELEGRAM_BOT_TOKEN = "8580738712:AAGCGZ5FR4QlQMpCmpbUjwWk46VL73w21DQ"
TELEGRAM_CHAT_ID = "-1004347624823"

GRAPHQL_URL = "https://redehidrometeorologica.defesacivil.rs.gov.br/graphql"

def iniciar_servidor_web_render():
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            print(f"🌐 Servidor Web do Render ativo na porta {port}")
            httpd.serve_forever()
    except Exception as e:
        print(f"Aviso servidor web: {e}")

# Regra de Subida Repentina (30 cm em 10 min)
LIMITE_SUBIDA_REPENTINA = 0.30  

# Novas Cotas Calibradas para a Vila Rosa
CHECKPOINTS = [108.30, 111.00, 112.00]

ultimo_nivel = None
ultimo_checkpoint_alertado = None
ultimo_dia_sinal_vida = None
primeira_leitura = True  # Inicialização silenciosa ativada

query = """
query GetTags {
  tags_data(
    clients: ["casa-militar-defesa-civil-rs"],
    station: ["DCRS-00085"]
  ) {
    qualle_meteorologia {
      codigo
      data {
        rio {
          rio_nivel {
            value
          }
        }
      }
    }
  }
}
"""

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://redehidrometeorologica.defesacivil.rs.gov.br",
    "Referer": "https://redehidrometeorologica.defesacivil.rs.gov.br/"
}

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload)
        if res.status_code == 200:
            print("🟢 Mensagem enviada no Grupo!")
        else:
            print(f"🔴 Erro no Telegram: {res.text}")
    except Exception as e:
        print(f"🔴 Erro de conexão com o Telegram: {e}")

def verificar_sinal_de_vida(nivel_atual):
    global ultimo_dia_sinal_vida
    hoje = time.strftime('%Y-%m-%d')
    hora_atual = time.strftime('%H')

    if hora_atual == "08" and ultimo_dia_sinal_vida != hoje:
        msg_sinal = (
            f"🟢 *SISTEMA OPERACIONAL (SINAL DE VIDA)* 🟢\n\n"
            f"📅 *Data/Hora:* {time.strftime('%d/%m/%Y - %H:%M')}\n"
            f"🌊 *Nível Atual do Arroio:* {nivel_atual:.2f} m\n\n"
            f"🤖 _O monitoramento automático segue ativo 24 horas por dia._"
        )
        enviar_telegram(msg_sinal)
        ultimo_dia_sinal_vida = hoje

def analisar_e_alertar(nivel_atual):
    global ultimo_nivel, ultimo_checkpoint_alertado, primeira_leitura
    
    checkpoint_atingido = None
    for cp in sorted(CHECKPOINTS):
        if nivel_atual >= cp:
            checkpoint_atingido = cp

    # INICIALIZAÇÃO SILENCIOSA: grava estado atual sem avisos falsos ao religar
    if primeira_leitura:
        ultimo_nivel = nivel_atual
        ultimo_checkpoint_alertado = checkpoint_atingido
        primeira_leitura = False
        print(f"⚙️ Calibração inicial: Nível {nivel_atual:.2f} m | Checkpoint base: {checkpoint_atingido}")
        return

    # 1. VERIFICAÇÃO DE SUBIDA REPENTINA (30 cm em 10 min)
    if ultimo_nivel is not None:
        variacao = nivel_atual - ultimo_nivel
        if variacao >= LIMITE_SUBIDA_REPENTINA:
            msg = (
                f"🚨 *ALERTA DE SUBIDA REPENTINA* 🚨\n\n"
                f"⚠️ O Arroio Feitoria subiu muito rápido!\n"
                f"📈 *Aumento:* +{variacao:.2f} m em 10 minutos.\n"
                f"🌊 *Nível Atual:* {nivel_atual:.2f} m\n\n"
                f"Risco de enxurrada. Fiquem atentos!"
            )
            enviar_telegram(msg)

    # 2. SUBIDA PARA UM NOVO CHECKPOINT
    if checkpoint_atingido is not None:
        if ultimo_checkpoint_alertado is None or checkpoint_atingido > ultimo_checkpoint_alertado:
            if checkpoint_atingido == 108.30:
                msg = (
                    f"ℹ️ *INFORMATIVO DE TRÂNSITO LOCAL*\n\n"
                    f"🌊 *Nível do Arroio:* {nivel_atual:.2f} m\n"
                    f"📍 *Atenção:* Lâmina d'água passando sobre a ponte (final da *Rua Esporte Clube Vila Rosa*).\n"
                    f"🚗 Atenção ao trafegar pela ponte. Residências sem risco no momento."
                )
            elif checkpoint_atingido == 111.00:
                msg = (
                    f"🟡 *ALERTA DE PROXIMIDADE*\n\n"
                    f"🌊 *Nível do Arroio:* {nivel_atual:.2f} m\n"
                    f"⚠️ *Situação:* A água está próxima das residências, mas ainda sem atingir os pátios habitados.\n"
                    f"📋 Acompanhamento atento das lideranças comunitárias."
                )
            else:  # >= 112.00
                msg = (
                    f"🚨 *ALERTA CRÍTICO - ÁGUA NAS CASAS* 🚨\n\n"
                    f"🌊 *Nível do Arroio:* {nivel_atual:.2f} m\n"
                    f"⚠️ *Situação Crítica:* A água começou a invadir as primeiras casas e terrenos da Vila Rosa.\n"
                    f"📦 *Ação:* Retirem os veículos das áreas baixas e iniciem a evacuação preventiva das residências atingidas!"
                )

            enviar_telegram(msg)
            ultimo_checkpoint_alertado = checkpoint_atingido

    # 3. RECUO (RIO BAIXANDO)
    if ultimo_checkpoint_alertado is not None and (checkpoint_atingido is None or checkpoint_atingido < ultimo_checkpoint_alertado):
        msg_recuo = (
            f"🟢 *O NÍVEL DO ARROIO COMEÇOU A BAIXAR* 🟢\n\n"
            f"🌊 *Nível Medido:* {nivel_atual:.2f} m\n"
            f"📉 *Status:* O rio recuou para baixo da cota de {ultimo_checkpoint_alertado:.2f} m.\n\n"
            f"ℹ️ A água está recuando. Mantenham a atenção até a normalização."
        )
        enviar_telegram(msg_recuo)
        ultimo_checkpoint_alertado = checkpoint_atingido

    ultimo_nivel = nivel_atual

def consultar_estacao():
    try:
        response = requests.post(GRAPHQL_URL, json={"query": query}, headers=headers, timeout=15)
        
        if response.status_code == 200:
            dados = response.json()
            resultado = dados["data"]["tags_data"]["qualle_meteorologia"][0]
            nivel_atual = float(resultado["data"]["rio"]["rio_nivel"]["value"])
            
            hora = time.strftime('%H:%M:%S')
            print(f"[{hora}] Consulta realizada | Nível lido: {nivel_atual:.2f} m")
            
            verificar_sinal_de_vida(nivel_atual)
            analisar_e_alertar(nivel_atual)
        else:
            print(f"[{time.strftime('%H:%M:%S')}] Erro na API Defesa Civil: HTTP {response.status_code}")
        
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Erro na consulta: {e}")

if __name__ == "__main__":
    threading.Thread(target=iniciar_servidor_web_render, daemon=True).start()
    
    print("Iniciando Monitoramento do Arroio Feitoria...")
    enviar_telegram("🤖 O sistema de alertas de enchente foi REINICIADO com as novas cotas e está monitorando o leito do rio.")
    
    consultar_estacao()
    
    while True:
        time.sleep(600)  # Checa a cada 10 minutos
        consultar_estacao()
