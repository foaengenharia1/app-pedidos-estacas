import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import uuid
from datetime import datetime
import pandas as pd
from fpdf import FPDF
import json

# --- FUNÇÃO PARA GERAR O PDF ---
def gerar_recibo_pdf(id_pedido, data, solicitante, cliente, obra, data_desejada, obs, carrinho):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Comprovante de Pedido - Estacas", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, f"ID do Pedido: {id_pedido}", ln=True)
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 8, f"Data da Solicitacao: {data}", ln=True)
    pdf.cell(0, 8, f"Solicitante: {solicitante}", ln=True)
    pdf.cell(0, 8, f"Cliente/Empresa: {cliente}", ln=True)
    pdf.cell(0, 8, f"Obra/Local: {obra}", ln=True)
    pdf.cell(0, 8, f"Data Desejada: {data_desejada}", ln=True)
    if obs:
        pdf.cell(0, 8, f"Observacoes: {obs}", ln=True)
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 10, "Itens Solicitados:", ln=True)
    pdf.set_font("helvetica", "", 12)
    for item in carrinho:
        texto_item = f"- {item['Quantidade']}x modelo {item['Modelo']} ({item['Comprimento']}m) | Metragem: {item['Metragem Total']}m"
        pdf.cell(0, 8, texto_item, ln=True)
    return bytes(pdf.output())

# --- 1. CONFIGURAÇÃO E MEMÓRIA (CACHE) ---
escopos = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# 1.1 Cache da Conexão: Faz o login apenas 1 vez e guarda a conexão aberta
@st.cache_resource
def conectar_planilha():
    creds_dict = json.loads(st.secrets["google_credentials"])
    credenciais = Credentials.from_service_account_info(creds_dict, scopes=escopos)
    cliente_gspread = gspread.authorize(credenciais)
    return cliente_gspread.open("Sistema de Logística - Estacas") # ⚠️ Lembre-se de colocar o nome da sua planilha aqui

# 1.2 Cache dos Dados: Lê a aba CADASTROS e guarda na memória por 10 minutos (600 segundos)
@st.cache_data(ttl=600)
def buscar_cadastros():
    planilha = conectar_planilha()
    aba_cadastros = planilha.worksheet("CADASTROS")
    aba_metragens = planilha.worksheet("Cadastros_Metragens")
    modelos = aba_cadastros.col_values(1)[1:]
    comprimentos = aba_metragens.col_values(1)[1:]
    return modelos, comprimentos

# Tenta conectar e puxar os dados usando a memória
try:
    planilha = conectar_planilha()
    aba_pedidos = planilha.worksheet("Pedidos")
    aba_itens = planilha.worksheet("Itens_Pedido")
    
    lista_modelos, lista_comprimentos = buscar_cadastros()
    
    if not lista_modelos: lista_modelos = ["Sem modelos"]
    if not lista_comprimentos: lista_comprimentos = ["0"]

except Exception as e:
    st.error(f"Erro ao conectar com o Google Sheets: {e}")
    st.stop()

# --- 2. MEMÓRIA DO APP (CARRINHO) ---
if 'carrinho' not in st.session_state:
    st.session_state['carrinho'] = []

st.set_page_config(page_title="Pedido de Estacas", page_icon="📦")

# --- TELA DE SUCESSO E DOWNLOAD ---
if 'pdf_pronto' in st.session_state:
    st.title("✅ Pedido Concluído!")
    st.success("Seu pedido foi recebido com sucesso pela nossa equipe de logística.")
    st.download_button(
        label="📄 Baixar Comprovante em PDF",
        data=st.session_state['pdf_pronto'],
        file_name=f"Pedido_{st.session_state['id_pedido']}.pdf",
        mime="application/pdf",
        type="primary"
    )
    st.divider()
    if st.button("🔄 Fazer Novo Pedido"):
        del st.session_state['pdf_pronto']
        del st.session_state['id_pedido']
        st.rerun()
    st.stop() 

# --- 3. O VISUAL DO FORMULÁRIO ---

# Adiciona a logo da empresa
# (Substitua "logo.png" pelo nome exato do seu arquivo de imagem)
try:
    st.image("logo.png", width=750) # O width controla a largura da imagem. Pode aumentar ou diminuir.
except:
    pass # Se ele não achar a imagem, ele ignora e não quebra o app
st.title("📦 Solicitação de Estacas")

st.subheader("1. Dados do Cliente e Entrega")
col_a1, col_a2 = st.columns(2)

with col_a1:
    solicitante = st.text_input("Nome do Solicitante *")
    cliente_empresa = st.text_input("Cliente / Empresa *")

with col_a2:
    obra_local = st.text_input("Obra / Local de Entrega *")
    data_desejada = st.date_input("Data Desejada para Entrega", format="DD/MM/YYYY")

observacoes = st.text_area("Observações Gerais (Opcional)")

st.divider() 

st.subheader("2. Adicionar Estacas ao Pedido")
col_b1, col_b2, col_b3 = st.columns(3)

with col_b1:
    modelo = st.selectbox("Estaca", lista_modelos)
with col_b2:
    comprimento = st.selectbox("Comprimento (m)", lista_comprimentos)
with col_b3:
    quantidade = st.number_input("Quantidade (m)", min_value=1, step=1)

if st.button("➕ Adicionar ao Pedido"):
    metragem_total = quantidade * int(comprimento)
    st.session_state['carrinho'].append({
        "Modelo": modelo,
        "Comprimento(m)": comprimento,
        "Quantidade(m)": quantidade,
        "Metragem Total (m)": metragem_total
    })
    st.success(f"{quantidade}m de Estaca {modelo} com {comprimento} adicionado(s) com sucesso!")

st.divider()

st.subheader("3. Resumo do Pedido")

if len(st.session_state['carrinho']) > 0:
    df_carrinho = pd.DataFrame(st.session_state['carrinho'])
    st.dataframe(df_carrinho, use_container_width=True)
    
    if st.button("🚀 Finalizar e Enviar Pedido", type="primary"):
        if solicitante == "" or cliente_empresa == "" or obra_local == "":
            st.warning("⚠️ Por favor, preencha os campos com asterisco (*) antes de enviar.")
        else:
            with st.spinner("A enviar pedido e a gerar PDF..."):
                id_pedido = str(uuid.uuid4())[:8].upper()
                data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
                data_desejada_str = data_desejada.strftime("%d/%m/%Y")
                
                try:
                    linha_pedido = [id_pedido, data_atual, solicitante, cliente_empresa, obra_local, data_desejada_str, observacoes, "Pendente"]
                    aba_pedidos.append_row(linha_pedido)
                    
                    para_inserir = []
                    for item in st.session_state['carrinho']:
                        id_item = str(uuid.uuid4())[:8].upper()
                        linha_item = [id_item, id_pedido, item["Modelo"], item["Comprimento"], item["Quantidade"], item["Metragem Total"]]
                        para_inserir.append(linha_item)
                    aba_itens.append_rows(para_inserir)
                    
                    pdf_bytes = gerar_recibo_pdf(id_pedido, data_atual, solicitante, cliente_empresa, obra_local, data_desejada_str, observacoes, st.session_state['carrinho'])
                    
                    st.session_state['pdf_pronto'] = pdf_bytes
                    st.session_state['id_pedido'] = id_pedido
                    st.session_state['carrinho'] = [] 
                    st.rerun() 
                    
                except Exception as e:
                    st.error(f"❌ Ocorreu um erro ao guardar: {e}")
else:
    st.info("O seu pedido ainda está vazio. Adicione estacas acima.")