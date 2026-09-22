import requests
import time
import os
import threading
import http.server
import socketserver
from datetime import datetime, timedelta, timezone

# ================= CONFIGURAÇÕES =================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "-1004347624823"
GRAPHQL_URL = "https://redehidrometeorologica.defesacivil.rs.gov.br/graphql"

# Ajuste de Fuso Horário para o Brasil (UTC-3)
fuso_br = timezone(timedelta(hours=-3))

def iniciar_servidor_web_render():
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            print(f"🌐 Servidor Web ativo na porta {port}")
            httpd.serve_forever()
    except Exception as e:
        pass

LIMITE_SUBIDA_REPENTINA = 0.30  
CHECKPOINTS = [108.30, 111.00, 112.00]

# Variáveis de Estado
ultimo_nivel = None
ultimo_checkpoint_alertado = None
ultimo_dia_boletim = None
primeira_leitura = True

# Variáveis do Alerta Periódico (Acima de 107m)
ultimo_tempo_periodico = 0
nivel_referencia_periodico = None
INTERVALO_PERIODICO = 3600  # 1 hora (em segundos)

query = """
query GetTags {
  tags_data(clients: ["casa-militar-defesa-civil-rs"], station: ["DCRS-00085"]) {
    qualle_meteorologia { data { rio { rio_nivel { value } } } }
  }
}
"""

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensagem, "parse_mode": "Markdown"})
    except:
        pass

def verificar_boletim_diario(nivel_atual):
    global ultimo_dia_boletim
    agora = datetime.now(fuso_br)
    hoje = agora.strftime('%Y-%m-%d')
    hora_atual = agora.strftime('%H')

    # Envia o boletim apenas às 08h do Horário de Brasília
    if hora_atual == "08" and ultimo_dia_boletim != hoje:
        msg = (
            f"📊 *BOLETIM DIÁRIO DE SITUAÇÃO*\n\n"
            f"📅 *Data:* {agora.strftime('%d/%m/%Y - %H:%M')}\n"
            f"🌊 *Nível Atual:* {nivel_atual:.2f} m\n\n"
            f"ℹ️ O nível encontra-se abaixo da cota de atenção. O monitoramento automático segue ativo 24h."
        )
        enviar_telegram(msg)
        ultimo_dia_boletim = hoje

def analisar_e_alertar(nivel_atual):
    global ultimo_nivel, ultimo_checkpoint_alertado, primeira_leitura
    global ultimo_tempo_periodico, nivel_referencia_periodico
    
    agora = datetime.now(fuso_br)
    agora_ts = time.time()
    
    checkpoint_atingido = None
    for cp in sorted(CHECKPOINTS):
        if nivel_atual >= cp:
            checkpoint_atingido = cp

    if primeira_leitura:
        ultimo_nivel = nivel_atual
        ultimo_checkpoint_alertado = checkpoint_atingido
        primeira_leitura = False
        return

    # 1. ALERTA DE SUBIDA REPENTINA
    if ultimo_nivel is not None:
        variacao = nivel_atual - ultimo_nivel
        if variacao >= LIMITE_SUBIDA_REPENTINA:
            msg = (
                f"🚨 *ALERTA DE SUBIDA RÁPIDA* 🚨\n\n"
                f"⚠️ O nível subiu +{variacao:.2f} m em apenas 10 minutos!\n"
                f"🌊 *Nível Atual:* {nivel_atual:.2f} m\n"
                f"Atenção para risco de enxurrada."
            )
            enviar_telegram(msg)

    # =========================================================
    # 2. REGRA DE ATUALIZAÇÕES DE HORA EM HORA (ACIMA DE 107m)
    # =========================================================
    if nivel_atual >= 107.00:
        if agora_ts - ultimo_tempo_periodico >= INTERVALO_PERIODICO:
            
            # Primeira vez que passa de 107m
            if nivel_referencia_periodico is None:
                msg = (
                    f"⚠️ *ESTADO DE ATENÇÃO ATIVADO*\n\n"
                    f"🌊 *Nível Atual:* {nivel_atual:.2f} m\n"
                    f"ℹ️ O arroio atingiu 107m. A partir de agora, o sistema enviará *alertas de hora em hora* relatando a tendência (subindo/baixando/estável)."
                )
                enviar_telegram(msg)
            else:
                # Calcula se subiu ou baixou na última hora
                diff = nivel_atual - nivel_referencia_periodico
                if diff >= 0.03:
                    tendencia = f"📈 *SUBINDO* (+{diff:.2f} m na última hora)"
                elif diff <= -0.03:
                    tendencia = f"📉 *BAIXANDO* ({abs(diff):.2f} m na última hora)"
                else:
                    tendencia = "➖ *ESTÁVEL*"

                msg = (
                    f"⏱️ *ALERTA DE HORA EM HORA (Acima de 107m)*\n\n"
                    f"🌊 *Nível Atual:* {nivel_atual:.2f} m\n"
                    f"📊 *Tendência:* {tendencia}"
                )
                enviar_telegram(msg)
            
            nivel_referencia_periodico = nivel_atual
            ultimo_tempo_periodico = agora_ts
            
    # Se estava acima de 107 e baixou
    else:
        if nivel_referencia_periodico is not None:
            msg = (
                f"✅ *ESTADO DE ATENÇÃO ENCERRADO*\n\n"
                f"🌊 *Nível Atual:* {nivel_atual:.2f} m\n"
                f"ℹ️ O nível retornou para a cota de normalidade (abaixo de 107m). Os alertas de hora em hora foram suspensos e *os avisos voltam a ser exclusivamente diários (às 08h)*."
            )
            enviar_telegram(msg)
            nivel_referencia_periodico = None
            ultimo_tempo_periodico = 0

    # =========================================================
    # 3. VERIFICAÇÃO DE CHECKPOINTS OFICIAIS (Ponte, casas)
    # =========================================================
    if checkpoint_atingido is not None:
        if ultimo_checkpoint_alertado is None or checkpoint_atingido > ultimo_checkpoint_alertado:
            if checkpoint_atingido == 108.30:
                msg = f"ℹ️ *AVISO DE TRÂNSITO LOCAL*\n\n🌊 *Nível:* {nivel_atual:.2f} m\n📍 Lâmina d'água passando sobre a ponte da *Rua Esporte Clube*. Atenção."
            elif checkpoint_atingido == 111.00:
                msg = f"🟡 *ALERTA DE PROXIMIDADE*\n\n🌊 *Nível:* {nivel_atual:.2f} m\n⚠️ A água está próxima das residências."
            else:
                msg = f"🚨 *ALERTA CRÍTICO - ÁGUA NAS CASAS* 🚨\n\n🌊 *Nível:* {nivel_atual:.2f} m\n⚠️ A água começou a invadir pátios e casas. Iniciar evacuação preventiva!"

            enviar_telegram(msg)
            ultimo_checkpoint_alertado = checkpoint_atingido

    ultimo_nivel = nivel_atual

def consultar_estacao():
    try:
        response = requests.post(GRAPHQL_URL, json={"query": query}, headers=headers, timeout=15)
        if response.status_code == 200:
            dados = response.json()
            resultado = dados["data"]["tags_data"]["qualle_meteorologia"][0]
            nivel_atual = float(resultado["data"]["rio"]["rio_nivel"]["value"])
            
            print(f"Leitura OK: {nivel_atual:.2f} m")
            verificar_boletim_diario(nivel_atual)
            analisar_e_alertar(nivel_atual)
    except Exception as e:
        pass

if __name__ == "__main__":
    threading.Thread(target=iniciar_servidor_web_render, daemon=True).start()
    enviar_telegram("🤖 Sistema ATUALIZADO. Mensagens de mudança de estado (hora em hora / diário) configuradas com sucesso.")
    
    consultar_estacao()
    while True:
        time.sleep(600)
        consultar_estacao()
