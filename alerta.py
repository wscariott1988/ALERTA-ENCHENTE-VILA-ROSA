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

# Servidor Web de fachada para o Render não desligar a aplicação
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

# Checkpoints (Base Normal ~105.50m)
CHECKPOINTS = [
    106.50, # Atenção (+1,00 m)
    107.50, # Alerta Moderado (+2,00 m)
    108.50, # ALERTA CRÍTICO / Gordurinha (+3,00 m - Falta 50 cm para alagar)
    109.00, # TRANSBORDAMENTO (+3,50 m)
    110.00  # Inundação Severa (+4,50 m)
]

ultimo_nivel = None
ultimo_checkpoint_alertado = None

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
    "Content-Type": "application/json"
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
        print(f"🔴 Erro de conexão: {e}")

def analisar_e_alertar(nivel_atual):
    global ultimo_nivel, ultimo_checkpoint_alertado
    
    # 1. SUBIDA REPENTINA
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

    # 2. CHECKPOINTS DE ALTURA
    checkpoint_atingido = None
    for cp in sorted(CHECKPOINTS):
        if nivel_atual >= cp:
            checkpoint_atingido = cp

    if checkpoint_atingido is not None:
        if ultimo_checkpoint_alertado is None or checkpoint_atingido > ultimo_checkpoint_alertado:
            if checkpoint_atingido >= 109.00:
                icone, status, acao = "🔴", "*TRANSBORDAMENTO ATINGIDO*", "A água está saindo da calha do arroio!"
            elif checkpoint_atingido == 108.50:
                icone, status, acao = "🟠", "*ALERTA CRÍTICO (Gordurinha de Segurança)*", "Levantem móveis e retirem os carros das áreas baixas!"
            else:
                icone, status, acao = "🟡", "*NÍVEL DE ATENÇÃO*", "O nível do arroio está subindo."

            msg = (
                f"{icone} *ATUALIZAÇÃO DE NÍVEL* {icone}\n\n"
                f"{status}\n"
                f"📍 *Cota:* {checkpoint_atingido:.2f} m\n"
                f"🌊 *Nível Medido:* {nivel_atual:.2f} m\n\n"
                f"⚠️ *Ação:* {acao}"
            )
            enviar_telegram(msg)
            ultimo_checkpoint_alertado = checkpoint_atingido

    # 3. RECUO (RIO BAIXANDO)
    if ultimo_checkpoint_alertado is not None and (checkpoint_atingido is None or checkpoint_atingido < ultimo_checkpoint_alertado):
        msg_recuo = (
            f"🟢 *O NÍVEL DO ARROIO COMEÇOU A BAIXAR* 🟢\n\n"
            f"🌊 *Nível Medido:* {nivel_atual:.2f} m\n"
            f"📉 *Status:* O rio recuou para baixo da cota de {ultimo_checkpoint_alertado:.2f} m.\n\n"
            f"ℹ️ A água está recuando. Mantenham a atenção."
        )
        enviar_telegram(msg_recuo)
        ultimo_checkpoint_alertado = checkpoint_atingido

    ultimo_nivel = nivel_atual

def consultar_estacao():
    try:
        response = requests.post(GRAPHQL_URL, json={"query": query}, headers=headers, timeout=15)
        dados = response.json()
        
        resultado = dados["data"]["tags_data"]["qualle_meteorologia"][0]
        nivel_atual = float(resultado["data"]["rio"]["rio_nivel"]["value"])
        
        hora = time.strftime('%H:%M:%S')
        print(f"[{hora}] Consulta realizada | Nível lido: {nivel_atual:.2f} m")
        
        analisar_e_alertar(nivel_atual)
        
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Erro na consulta: {e}")

if __name__ == "__main__":
    # Inicia o servidor web em paralelo
    threading.Thread(target=iniciar_servidor_web_render, daemon=True).start()
    
    print("Iniciando Monitoramento do Arroio Feitoria...")
    enviar_telegram("🤖 O sistema de alertas de enchente foi LIGADO no Render e está monitorando o nível do rio.")
    
    consultar_estacao()
    
    while True:
        time.sleep(600)  # Checa a cada 10 minutos
        consultar_estacao()