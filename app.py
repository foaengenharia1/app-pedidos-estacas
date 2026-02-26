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
    
    # Título
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Comprovante de Pedido - Estacas", ln=True, align="C")
    pdf.ln(5)
    
    # Dados do Pedido
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
    
    # Itens do Pedido
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 10, "Itens Solicitados:", ln=True)
    pdf.set_font("helvetica", "", 12)
    
    for item in carrinho:
        texto_item = f"- {item['Quantidade']}x modelo {item['Modelo']} ({item['Comprimento']}m) | Total: {item['Metragem Total']}m"
        pdf.cell(0, 8, texto_item, ln=True)
        
    # Retorna o PDF em formato de bytes para o Streamlit baixar
    return bytes(pdf.output())

# --- 1. CONFIGURAÇÃO DO GOOGLE SHEETS ---
escopos = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

try:
    creds_dict = json.loads(st.secrets["google_credentials"])
    credenciais = Credentials.from_service_account_info(creds_dict, scopes=escopos)
    cliente = gspread.authorize(credenciais)
    
    # ⚠️ MUITO IMPORTANTE: Mantenha o nome exato do seu ficheiro no Google Drive
    planilha = cliente.open("Sistema de Logística - Estacas") 
    aba_pedidos = planilha.worksheet("Pedidos")       # Confirme as maiúsculas/minúsculas
    aba_itens = planilha.worksheet("Itens_Pedido")    # Confirme as maiúsculas/minúsculas
    aba_cadastros = planilha.worksheet("CADASTROS")   # <-- NOVA ABA AQUI
    aba_cadastros_metragens = planilha.worksheet("Cadastros_Metragens")
    
    # --- BUSCAR DADOS DINÂMICOS ---
    # col_values(1) pega na primeira coluna. O [1:] serve para ignorar o cabeçalho (linha 1)
    lista_modelos = aba_cadastros.col_values(1)[1:]
    lista_comprimentos = aba_cadastros_metragens.col_values(1)[1:]
    
    # Se por acaso a lista vier vazia, colocamos uma opção padrão para não dar erro
    if not lista_modelos:
        lista_modelos = ["Sem modelos cadastrados"]
    if not lista_comprimentos:
        lista_comprimentos = ["0"]

except Exception as e:
    st.error(f"Erro ao conectar com o Google Sheets: {e}")
    st.stop()

# --- 2. MEMÓRIA DO APP ---
if 'carrinho' not in st.session_state:
    st.session_state['carrinho'] = []

st.set_page_config(page_title="Pedido de Estacas", page_icon="📦")

# --- TELA DE SUCESSO E DOWNLOAD (Se o PDF estiver pronto) ---
if 'pdf_pronto' in st.session_state:
    st.title("✅ Pedido Concluído!")
    st.success("Seu pedido foi recebido com sucesso pela nossa equipe de logística.")
    
    # Botão de Download do PDF
    st.download_button(
        label="📄 Baixar Comprovante em PDF",
        data=st.session_state['pdf_pronto'],
        file_name=f"Pedido_{st.session_state['id_pedido']}.pdf",
        mime="application/pdf",
        type="primary"
    )
    
    st.divider()
    
    # Botão para limpar tudo e voltar ao formulário
    if st.button("🔄 Fazer Novo Pedido"):
        del st.session_state['pdf_pronto']
        del st.session_state['id_pedido']
        st.rerun()
        
    st.stop() # Para a leitura do código aqui. O formulário abaixo não aparece até ele clicar em Novo Pedido.


# --- 3. O VISUAL DO FORMULÁRIO ---
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
    modelo = st.selectbox("Modelo da Estaca", lista_modelos)
with col_b2:
    comprimento = st.selectbox("Comprimento (Metros)", lista_comprimentos)
with col_b3:
    quantidade = st.number_input("Quantidade", min_value=1, step=1)

if st.button("➕ Adicionar ao Pedido"):
    metragem_total = quantidade * int(comprimento)
    st.session_state['carrinho'].append({
        "Modelo": modelo,
        "Comprimento": comprimento,
        "Quantidade": quantidade,
        "Metragem Total": metragem_total
    })
    st.success(f"{quantidade}x {modelo} adicionado(s) com sucesso!")

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
                    # 1. Salva na aba PEDIDOS
                    linha_pedido = [id_pedido, data_atual, solicitante, cliente_empresa, obra_local, data_desejada_str, observacoes, "Pendente"]
                    aba_pedidos.append_row(linha_pedido)
                    
                    # 2. Salva na aba ITENS
                    para_inserir = []
                    for item in st.session_state['carrinho']:
                        id_item = str(uuid.uuid4())[:8].upper()
                        linha_item = [id_item, id_pedido, item["Modelo"], item["Comprimento"], item["Quantidade"], item["Metragem Total"]]
                        para_inserir.append(linha_item)
                    aba_itens.append_rows(para_inserir)
                    
                    # 3. GERA O PDF E SALVA NA MEMÓRIA
                    pdf_bytes = gerar_recibo_pdf(id_pedido, data_atual, solicitante, cliente_empresa, obra_local, data_desejada_str, observacoes, st.session_state['carrinho'])
                    
                    st.session_state['pdf_pronto'] = pdf_bytes
                    st.session_state['id_pedido'] = id_pedido
                    st.session_state['carrinho'] = [] # Limpa o carrinho
                    
                    # 4. Recarrega a página para mostrar a tela de sucesso
                    st.rerun() 
                    
                except Exception as e:
                    st.error(f"❌ Ocorreu um erro ao guardar: {e}")
else:
    st.info("O seu pedido ainda está vazio. Adicione estacas acima.")