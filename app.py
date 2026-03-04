import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import uuid
from datetime import datetime, timedelta, timezone 
import pandas as pd
from fpdf import FPDF
import json

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema de Logística", page_icon="📦", layout="wide") 

# --- 0. TELA DE LOGIN (SEGURANÇA E PERFIS) ---
SENHA_CLIENTE = st.secrets["senha_cliente"]
SENHA_ADMIN = st.secrets["senha_admin"] 

if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
    st.session_state['perfil'] = ""

if not st.session_state['autenticado']:
    try:
        st.image("logo.png", width=200)
    except:
        pass
    
    st.title("🔒 Acesso ao Sistema")
    st.markdown("Insira a sua senha de acesso.")
    
    senha_digitada = st.text_input("Senha", type="password")
    
    if st.button("Entrar", type="primary"):
        if senha_digitada == SENHA_CLIENTE:
            st.session_state['autenticado'] = True
            st.session_state['perfil'] = "cliente"
            st.rerun() 
        elif senha_digitada == SENHA_ADMIN:
            st.session_state['autenticado'] = True
            st.session_state['perfil'] = "admin"
            st.rerun()
        else:
            st.error("❌ Senha incorreta.")
            
    st.stop() 

# --- 1. CONFIGURAÇÃO E MEMÓRIA (CACHE) ---
escopos = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def conectar_planilha():
    creds_dict = json.loads(st.secrets["google_credentials"])
    credenciais = Credentials.from_service_account_info(creds_dict, scopes=escopos)
    cliente_gspread = gspread.authorize(credenciais)
    return cliente_gspread.open("Sistema de Logística - Estacas") 

@st.cache_data(ttl=600)
def buscar_cadastros():
    planilha = conectar_planilha()
    aba_cadastros = planilha.worksheet("CADASTROS")
    aba_metragens = planilha.worksheet("Cadastros_Metragens")
    modelos = aba_cadastros.col_values(1)[1:]
    comprimentos = aba_metragens.col_values(1)[1:]
    return modelos, comprimentos

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


# ==========================================
# ÁREA DO ADMINISTRADOR (Painel Unificado)
# ==========================================
if st.session_state['perfil'] == "admin":
    st.title("⚙️ Painel do Administrador")
    
    col_btn1, col_btn2 = st.columns([1, 10])
    with col_btn1:
        if st.button("🔄 Atualizar Dados"):
            st.rerun()
    with col_btn2:
        if st.button("Sair / Logout"):
            st.session_state['autenticado'] = False
            st.session_state['perfil'] = ""
            st.rerun()

    st.divider()
    
    with st.spinner("A carregar e processar dados do banco..."):
        try:
            dados_pedidos = aba_pedidos.get_all_values()
            dados_itens = aba_itens.get_all_values()
            
            if len(dados_pedidos) > 1:
                df_pedidos = pd.DataFrame(dados_pedidos[1:], columns=dados_pedidos[0])
                df_itens = pd.DataFrame(dados_itens[1:], columns=dados_itens[0]) if len(dados_itens) > 1 else pd.DataFrame()
                
                # --- 1. FILTRO DE DATA ---
                st.subheader("Filtro de Pedidos")
                col_data_desejada = df_pedidos.columns[5]
                
                usar_filtro = st.toggle("Filtrar por uma data específica", value=False)
                
                if usar_filtro:
                    data_selecionada = st.date_input("📅 Selecione a Data para visualização:", format="DD/MM/YYYY")
                    data_str = data_selecionada.strftime("%d/%m/%Y")
                    df_pedidos_filtrado = df_pedidos[df_pedidos[col_data_desejada] == data_str]
                    data_exibicao = data_str
                else:
                    df_pedidos_filtrado = df_pedidos
                    data_exibicao = "Todas as Datas"
                    
                st.write("") 
                
                # --- 2. CARDS DE RESUMO E TABELA ---
                if not df_pedidos_filtrado.empty:
                    col_m1, col_m2 = st.columns(2)
                    col_m1.metric("Total de Pedidos (Cargas)", len(df_pedidos_filtrado))
                    col_m2.metric("Data Analisada", data_exibicao)
                    
                    st.divider()
                    
                    st.subheader("📋 Lista de Pedidos")
                    df_pedidos_inverso = df_pedidos_filtrado.iloc[::-1]
                    st.dataframe(df_pedidos_inverso, use_container_width=True, hide_index=True)
                    
                    st.divider()
                    
                    # --- 3. GESTÃO, DETALHES E STATUS ---
                    st.subheader("🔍 Detalhes e Atualização de Status")
                    
                    # A lista de IDs agora acompanha o filtro de data!
                    lista_ids = [str(id) for id in df_pedidos_filtrado[df_pedidos_filtrado.columns[0]].tolist() if str(id).strip() != ""]
                    
                    pedido_selecionado = st.selectbox("Selecione o ID do Pedido para visualizar os detalhes:", [""] + lista_ids)
                    
                    if pedido_selecionado != "":
                        info_pedido = df_pedidos[df_pedidos[df_pedidos.columns[0]] == pedido_selecionado].iloc[0]
                        
                        st.markdown(f"### 📦 Itens do Pedido: **{pedido_selecionado}**")
                        st.info(f"**Cliente:** {info_pedido[df_pedidos.columns[3]]} | **Obra:** {info_pedido[df_pedidos.columns[4]]} | **Veículo:** {info_pedido[df_pedidos.columns[6]]}")
                        
                        if not df_itens.empty:
                            itens_do_pedido = df_itens[df_itens[df_itens.columns[1]] == pedido_selecionado]
                            if not itens_do_pedido.empty:
                                colunas_mostrar = [df_itens.columns[2], df_itens.columns[3], df_itens.columns[4], df_itens.columns[5], df_itens.columns[6]]
                                st.dataframe(itens_do_pedido[colunas_mostrar], use_container_width=True, hide_index=True)
                            else:
                                st.warning("Nenhum item encontrado para este pedido.")
                        else:
                            st.warning("A base de itens está vazia.")
                            
                        st.write("")
                        st.markdown("#### 🔄 Mudar o Status deste Pedido")
                        
                        col_s1, col_s2 = st.columns([2, 2])
                        
                        with col_s1:
                            status_atual = info_pedido[df_pedidos.columns[8]]
                            opcoes_status = ["Pendente", "Em Produção", "Em Transporte", "Entregue", "Cancelado"]
                            index_atual = opcoes_status.index(status_atual) if status_atual in opcoes_status else 0
                            novo_status = st.selectbox("Novo Status", opcoes_status, index=index_atual)
                        
                        with col_s2:
                            st.write("") 
                            st.write("") 
                            if st.button("Gravar Novo Status", type="primary"):
                                with st.spinner("A atualizar no Google Sheets..."):
                                    celula_id = aba_pedidos.find(pedido_selecionado)
                                    if celula_id:
                                        aba_pedidos.update_cell(celula_id.row, 9, novo_status)
                                        st.success(f"✅ Pedido {pedido_selecionado} alterado para: {novo_status}")
                                        st.rerun() 
                                    else:
                                        st.error("❌ ID não encontrado na folha de cálculo.")
                else:
                    st.warning("⚠️ Nenhum pedido encontrado para a data selecionada.")
                    
            else:
                st.warning("Ainda não há nenhum pedido registado na folha de cálculo.")
                
        except Exception as e:
            st.error(f"Erro ao carregar os dados: {e}")
            
    st.stop() 

# ==========================================
# ÁREA DO CLIENTE (FORMULÁRIO DE PEDIDOS)
# ==========================================

PESO_POR_METRO = {
    "17x17": 70, "ICP360": 130, "ETR229": 66, "ETR269": 90, "ETR360": 137, 
    "ETR406": 159, "ETR445": 201, "ETR525": 250, "ETR605": 325, "ETR707": 400, "ETR809": 530
}
PESO_PADRAO = 100 

def gerar_recibo_pdf(id_pedido, data, solicitante, cliente, obra, data_desejada, veiculo, obs, carrinho):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Comprovante de Pedido - Estacas", ln=True, align="C")
    pdf.ln(5)
    pdf