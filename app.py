import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import uuid
from datetime import datetime, timedelta, timezone 
import pandas as pd
from fpdf import FPDF
import json
import base64  
import requests
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema de Logística", page_icon="📦", layout="wide") 

# --- 🎨 IDENTIDADE VISUAL ADAPTÁVEL (LIGHT/DARK MODE) E BOTÕES ARREDONDADOS ---
# --- 🎨 IDENTIDADE VISUAL CORPORATIVA (FORÇANDO O AZUL #044589) ---
st.markdown("""
    <style>
    /* 1. FORÇA A COR AZUL ESCURO EM TODO O TEXTO DA PÁGINA */
    .stApp, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, 
    .stApp p, .stApp label, .stApp span, div[data-testid="stMetricValue"], 
    div[data-baseweb="tab"] p, div[data-baseweb="tab"] span {
        color: #044589 !important; 
    }
    
    /* 2. BLINDAGEM DOS BOTÕES (Fundo Azul, Texto 100% Branco) */
    div.stButton > button, 
    div.stButton > button p, 
    div.stButton > button span {
        background-color: #044589 !important; 
        color: #FFFFFF !important; /* Branco absoluto */
        border-color: #044589 !important;
        font-weight: bold !important;
        border-radius: 30px !important;
    }
    
    div.stButton > button:hover, 
    div.stButton > button:hover p, 
    div.stButton > button:hover span {
        background-color: #065ab3 !important; 
        border-color: #065ab3 !important;
        color: #FFFFFF !important; 
    }

    /* 3. EXCEÇÕES (Preserva as cores das mensagens de Sucesso, Erro e Avisos) */
    div[data-testid="stAlert"] *, div[data-testid="stException"] * {
        color: inherit !important;
    }
    
    /* 4. LINHAS DIVISÓRIAS */
    hr {
        border-bottom: 2px solid #044589 !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 0. TELA DE LOGIN (SEGURANÇA E PERFIS) ---
SENHA_ADMIN = st.secrets["senha_admin"] 

if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
    st.session_state['perfil'] = ""
    st.session_state['cliente_nome'] = ""
    st.session_state['cnpj'] = ""
    st.session_state['obra_nome'] = ""
    st.session_state['transportadora'] = ""
    st.session_state['codigo_contrato'] = ""
    st.session_state['modelos_permitidos'] = []
    st.session_state['comprimentos_permitidos'] = []
    st.session_state['metragens_contratadas'] = {}
    st.session_state['carrinhos'] = {} 

# --- 1. CONFIGURAÇÃO DO GOOGLE SHEETS E MEMÓRIA (CACHE) ---
escopos = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def conectar_planilha():
    creds_dict = json.loads(st.secrets["google_credentials"])
    credenciais = Credentials.from_service_account_info(creds_dict, scopes=escopos)
    cliente_gspread = gspread.authorize(credenciais)
    return cliente_gspread.open("Sistema de Logística - TESTE")

@st.cache_resource
def obter_abas():
    planilha = conectar_planilha()
    aba_pedidos = planilha.worksheet("Pedidos")
    aba_itens = planilha.worksheet("Itens_Pedido")
    
    if len(aba_pedidos.row_values(1)) < 10:
        aba_pedidos.update_cell(1, 10, "Codigo_Contrato")

    try:
        aba_contratos = planilha.worksheet("Contratos")
    except:
        aba_contratos = planilha.add_worksheet(title="Contratos", rows="1000", cols="4")
        aba_contratos.append_row(["Codigo", "Cliente", "Obra", "Itens"])

    aba_cadastros = planilha.worksheet("CADASTROS")
    aba_metragens = planilha.worksheet("Cadastros_Metragens")
    
    try:
        aba_transportadoras = planilha.worksheet("Transportadoras")
    except:
        aba_transportadoras = planilha.add_worksheet(title="Transportadoras", rows="1000", cols="5")
        aba_transportadoras.append_row(["Nome", "CNPJ", "Endereco", "Telefone", "Email"])
    
    return aba_pedidos, aba_itens, aba_contratos, aba_cadastros, aba_metragens, aba_transportadoras

@st.cache_data(ttl=3600)
def buscar_cadastros_listas():
    _, _, _, aba_cadastros, aba_metragens, aba_transportadoras = obter_abas()
    lista_m = aba_cadastros.col_values(1)[1:]
    lista_c = aba_metragens.col_values(1)[1:]
    lista_t = aba_transportadoras.col_values(1)[1:]
    return lista_m, lista_c, lista_t

@st.cache_data(ttl=60)
def carregar_dados_planilhas():
    aba_pedidos, aba_itens, aba_contratos, _, _, _ = obter_abas()
    return aba_pedidos.get_all_values(), aba_itens.get_all_values(), aba_contratos.get_all_values()

try:
    aba_pedidos, aba_itens, aba_contratos, aba_cadastros, aba_metragens, aba_transportadoras = obter_abas()
    lista_modelos_geral, lista_comprimentos_geral, lista_transportadoras_geral = buscar_cadastros_listas()
    
    if not lista_modelos_geral: lista_modelos_geral = ["Sem modelos"]
    if not lista_comprimentos_geral: lista_comprimentos_geral = ["0"]
    if not lista_transportadoras_geral: lista_transportadoras_geral = [] 

except Exception as e:
    st.error(f"Erro ao conectar com o Google Sheets: {e}")
    st.stop()


def calcular_saldos(codigo_contrato, metragens_contratadas):
    dados_pedidos, dados_itens, _ = carregar_dados_planilhas()
    
    df_p = pd.DataFrame(dados_pedidos[1:], columns=dados_pedidos[0]) if len(dados_pedidos) > 1 else pd.DataFrame()
    df_i = pd.DataFrame(dados_itens[1:], columns=dados_itens[0]) if len(dados_itens) > 1 else pd.DataFrame()
    
    consumo = {}
    if not df_p.empty and len(df_p.columns) >= 10:
        pedidos_contrato = df_p[df_p[df_p.columns[9]] == codigo_contrato]
        ids_pedidos = pedidos_contrato[df_p.columns[0]].tolist()
        
        if ids_pedidos and not df_i.empty:
            itens_consumidos = df_i[df_i[df_i.columns[1]].isin(ids_pedidos)]
            for _, row in itens_consumidos.iterrows():
                mod = row[df_i.columns[2]]
                met = pd.to_numeric(row[df_i.columns[5]], errors='coerce')
                consumo[mod] = consumo.get(mod, 0) + met
                
    saldos = {}
    for mod, total_contratado in metragens_contratadas.items():
        saldos[mod] = total_contratado - consumo.get(mod, 0)
        
    return saldos, consumo


# ==========================================
# LÓGICA DA TELA DE LOGIN E PRIMEIRO ACESSO
# ==========================================
if not st.session_state['autenticado']:
    try:
        st.image("FOÁ ENGENHARIA.png", width=200)
    except:
        pass
    
    st.title("🔒 Acesso ao Portal")
    
    aba_login, aba_primeiro_acesso = st.tabs(["🔐 Login", "🆕 Primeiro Acesso (Criar Senha)"])
    
    with aba_login:
        st.markdown("Se já possui senha, preencha os dados abaixo. *A equipe interna deve digitar a senha Administrativa no campo 'Código de Acesso'.*")
        
        codigo_digitado = st.text_input("Código de Acesso (Contrato)", key="login_cod")
        senha_digitada = st.text_input("Senha do Cliente", type="password", key="login_sen")
        
        if st.button("Entrar", type="primary"):
            if codigo_digitado == SENHA_ADMIN:
                st.session_state['autenticado'] = True
                st.session_state['perfil'] = "admin"
                st.rerun() 
            elif codigo_digitado == "":
                st.warning("⚠️ Por favor, preencha o Código do Contrato.")
            else:
                with st.spinner("A verificar credenciais..."):
                    _, _, dados_contratos = carregar_dados_planilhas()
                    if len(dados_contratos) > 1:
                        df_contratos = pd.DataFrame(dados_contratos[1:], columns=dados_contratos[0])
                        
                        if codigo_digitado in df_contratos['Codigo'].values:
                            contrato = df_contratos[df_contratos['Codigo'] == codigo_digitado].iloc[0]
                            permissoes = json.loads(contrato['Itens'])
                            
                            senha_salva = permissoes.get('senha', '')
                            
                            if senha_salva == "":
                                st.warning("⚠️ Este contrato ainda não possui senha. Por favor, acesse a aba 'Primeiro Acesso' ao lado para criar.")
                            elif senha_salva == senha_digitada:
                                st.session_state['autenticado'] = True
                                st.session_state['perfil'] = "cliente"
                                st.session_state['cliente_nome'] = contrato['Cliente']
                                st.session_state['obra_nome'] = contrato['Obra']
                                st.session_state['codigo_contrato'] = codigo_digitado
                                st.session_state['carrinhos'] = {}
                                
                                st.session_state['cnpj'] = permissoes.get('cnpj', '')
                                st.session_state['transportadora'] = permissoes.get('transportadora', '')
                                st.session_state['modelos_permitidos'] = permissoes.get('modelos', [])
                                st.session_state['comprimentos_permitidos'] = permissoes.get('comprimentos', [])
                                st.session_state['metragens_contratadas'] = permissoes.get('metragens', {})
                                
                                st.rerun()
                            else:
                                st.error("❌ Senha incorreta.")
                        else:
                            st.error("❌ Código de Obra inválido ou não encontrado.")
                    else:
                        st.error("❌ Nenhum contrato registado no sistema.")
                        
    with aba_primeiro_acesso:
        st.markdown("Recebeu o seu **Código de Contrato** da fábrica? Insira-o abaixo para criar a sua senha de acesso exclusivo.")
        
        pa_codigo = st.text_input("Código do Contrato", key="pa_cod")
        pa_senha = st.text_input("Crie uma Senha", type="password", key="pa_sen1")
        pa_senha_conf = st.text_input("Confirme a Senha", type="password", key="pa_sen2")
        
        if st.button("Gravar Senha e Finalizar Cadastro", type="primary"):
            if pa_codigo == "" or pa_senha == "" or pa_senha_conf == "":
                st.warning("⚠️ Preencha todos os campos antes de continuar.")
            elif pa_senha != pa_senha_conf:
                st.error("⚠️ As senhas não coincidem. Digite novamente.")
            else:
                with st.spinner("A validar contrato e registar senha..."):
                    try:
                        celula = aba_contratos.find(pa_codigo, in_column=1)
                        valores_linha = aba_contratos.row_values(celula.row)
                        
                        itens_json = valores_linha[3]
                        permissoes = json.loads(itens_json)
                        
                        if permissoes.get('senha', '') != "":
                            st.error("❌ Este contrato já possui uma senha registada. Vá para a aba 'Login'.")
                        else:
                            permissoes['senha'] = pa_senha
                            novo_json = json.dumps(permissoes)
                            aba_contratos.update_cell(celula.row, 4, novo_json)
                            st.cache_data.clear() 
                            
                            st.success("✅ Senha registada com sucesso! Volte para a aba 'Login' e insira o seu contrato e senha para aceder.")
                            
                    except gspread.exceptions.CellNotFound:
                        st.error("❌ Código de Contrato não encontrado no sistema.")
                    except Exception as e:
                        st.error(f"❌ Ocorreu um erro ao processar o contrato: {e}")
                        
    st.stop() 


# ==========================================
# ÁREA DO ADMINISTRADOR
# ==========================================
if st.session_state['perfil'] == "admin":
    
    # Cabeçalho: Logo na esquerda, Título no meio, Botões na direita
    col_logo, col_titulo, col_botoes = st.columns([2, 5, 2])
    
    with col_logo:
        try:
            # Puxa a sua imagem salva na pasta
            st.image("FOÁ ENGENHARIA.png", use_container_width=True)
        except:
            st.warning("⚠️ Imagem FOÁ ENGENHARIA.png não encontrada.")
            
    with col_titulo:
        st.write("") # Espaçamento para alinhar verticalmente
        st.markdown("## ⚙️ Painel do Administrador")
        
    with col_botoes:
        st.write("") # Espaçamento
        if st.button("🔄 Atualizar"):
            st.cache_data.clear()
            st.rerun()
        if st.button("🚪 Sair / Logout"):
            st.session_state['autenticado'] = False
            st.session_state['perfil'] = ""
            st.rerun()

    st.divider()
    
    with st.spinner("A processar painéis..."):
        try:
            dados_pedidos, dados_itens, dados_contratos = carregar_dados_planilhas()
            
            df_pedidos = pd.DataFrame(dados_pedidos[1:], columns=dados_pedidos[0]) if len(dados_pedidos) > 1 else pd.DataFrame()
            df_itens = pd.DataFrame(dados_itens[1:], columns=dados_itens[0]) if len(dados_itens) > 1 else pd.DataFrame()
            df_contratos = pd.DataFrame(dados_contratos[1:], columns=dados_contratos[0]) if len(dados_contratos) > 1 else pd.DataFrame()
            
            # As abas do Streamlit
            tab_gestao, tab_cadastros = st.tabs(["📋 Gestão Operacional (Logística)", "📝 Contratos e Clientes"])
            
            with tab_gestao:
                st.subheader("📋 Painel de Despacho e Cargas")
                
                if df_pedidos.empty:
                    st.info("O sistema não possui nenhum pedido registado.")
                else:
                    col_filtro1, col_filtro2 = st.columns([1, 3])
                    with col_filtro1:
                        data_hoje = datetime.now().date()
                        data_filtro = st.date_input("📅 Selecione a Data de Entrega:", value=data_hoje, format="DD/MM/YYYY")
                        data_filtro_str = data_filtro.strftime("%d/%m/%Y")
                    
                    st.divider()
                    
                    df_pedidos['Data_Limpa'] = df_pedidos[df_pedidos.columns[5]].astype(str).str.strip()
                    df_filtro_dia = df_pedidos[df_pedidos['Data_Limpa'] == data_filtro_str]
                    
                    # 🔴 GAVETAS MÁGICAS: Criadas FORA da condição, para funcionarem mesmo no ZERO
                    gavetas = [st.empty() for _ in range(50)]
                    gaveta_idx = 0
                    
                    if df_filtro_dia.empty:
                        # Se não tem pedidos, usa a gaveta 0 para o aviso e avança
                        gavetas[gaveta_idx].info(f"Nenhuma carga agendada ou solicitada para o dia {data_filtro_str}.")
                        gaveta_idx += 1
                    else:
                        qtd_carretas = len(df_filtro_dia)
                        gavetas[gaveta_idx].success(f"**Resumo do Dia:** {qtd_carretas} Carreta(s) agendada(s) para {data_filtro_str}.")
                        gaveta_idx += 1
                        
                        clientes_do_dia = df_filtro_dia[df_filtro_dia.columns[3]].unique()
                        
                        for cliente in clientes_do_dia:
                            pedidos_do_cliente = df_filtro_dia[df_filtro_dia[df_filtro_dia.columns[3]] == cliente]
                            cod_contrato = pedidos_do_cliente.iloc[0][df_pedidos.columns[9]]
                            qtd_cliente = len(pedidos_do_cliente)
                            
                            with gavetas[gaveta_idx].container():
                                st.markdown(f"### 🏢 {cliente} | Contrato: {cod_contrato} | {qtd_cliente} Carreta(s)")
                            gaveta_idx += 1
                            
                            for _, row_ped in pedidos_do_cliente.iterrows():
                                id_ped = row_ped[df_pedidos.columns[0]]
                                veiculo_ped = row_ped[df_pedidos.columns[6]]
                                status_ped = row_ped[df_pedidos.columns[8]]
                                obs_ped = row_ped[df_pedidos.columns[7]]
                                
                                emoji = "🔵"
                                if status_ped == "Entregue": emoji = "🟢"
                                elif status_ped == "Cancelado": emoji = "🔴"
                                elif status_ped == "Em Transporte": emoji = "🟠"
                                
                                with gavetas[gaveta_idx].container():
                                    with st.expander(f"{emoji} Pedido: {id_ped} | Veículo: {veiculo_ped} | Status: {status_ped}"):
                                        st.info(f"**Observações do Cliente:** {obs_ped if obs_ped else 'Nenhuma'}")
                                        
                                        if not df_itens.empty:
                                            itens_deste = df_itens[df_itens[df_itens.columns[1]] == id_ped]
                                            if not itens_deste.empty:
                                                colunas_mostrar = [df_itens.columns[0], df_itens.columns[2], df_itens.columns[3], df_itens.columns[4], df_itens.columns[5], df_itens.columns[6]]
                                                df_mostrar = itens_deste[colunas_mostrar].copy()
                                                df_mostrar.columns = ["Cód. Item", "Modelo", "Comprimento (m)", "Quantidade", "Total (m)", "Peso (kg)"]
                                                st.dataframe(df_mostrar, use_container_width=True, hide_index=True)
                                            else:
                                                st.warning("Nenhum item na base de dados para esta carga.")
                                        
                                        st.markdown("#### 🔄 Atualizar Status da Carga")
                                        col_s1, col_s2, col_s3 = st.columns([2, 2, 2])
                                        with col_s1:
                                            opcoes_status = ["Pendente", "Em Produção", "Em Transporte", "Entregue", "Cancelado"]
                                            idx_status = opcoes_status.index(status_ped) if status_ped in opcoes_status else 0
                                            novo_status = st.selectbox("Novo Status:", opcoes_status, index=idx_status, key=f"sel_{id_ped}", label_visibility="collapsed")
                                        with col_s2:
                                            if st.button("Gravar Alteração", key=f"btn_{id_ped}", type="primary"):
                                                with st.spinner("Atualizando no Google Sheets..."):
                                                    celula_id = aba_pedidos.find(id_ped)
                                                    if celula_id:
                                                        aba_pedidos.update_cell(celula_id.row, 9, novo_status)
                                                        st.cache_data.clear()
                                                        st.rerun()
                                                    else:
                                                        st.error("Erro: Pedido não encontrado na planilha.")
                                gaveta_idx += 1
                                
                    # 🔴 LIMPEZA FINAL OBRIGATÓRIA: 
                    # Se o dia estava vazio, o gaveta_idx é 1. O código destrói os fantasmas do índice 1 ao 49!
                    for i in range(gaveta_idx, 50):
                        gavetas[i].empty()                   

            with tab_cadastros:
                col_cad1, col_cad2 = st.columns([1, 1])
                
                with col_cad1:
                    st.subheader("📝 Novo Contrato de Obra")
                    
                    # --- 1. BUSCA INTELIGENTE DE CNPJ ---
                    col_cnpj_input, col_cnpj_btn = st.columns([3, 1])
                    with col_cnpj_input:
                        c_cnpj = st.text_input("CNPJ (somente números) *")
                    with col_cnpj_btn:
                        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                        if st.button("🔍 Buscar", key="btn_busca_cnpj", type="secondary", use_container_width=True):
                            cnpj_limpo = re.sub(r'\D', '', c_cnpj)
                            if len(cnpj_limpo) == 14:
                                with st.spinner("Buscando CNPJ..."):
                                    try:
                                        res = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}", timeout=5)
                                        if res.status_code == 200:
                                            st.session_state['nome_cliente_temp'] = res.json().get('razao_social', '')
                                        else:
                                            st.error("CNPJ não encontrado.")
                                    except:
                                        st.error("Falha ao conectar com a Receita.")
                            else:
                                st.warning("Digite os 14 números do CNPJ.")
                    
                    c_cliente = st.text_input("Nome do Cliente / Empresa *", value=st.session_state.get('nome_cliente_temp', ''))

                    # --- 2. BUSCA INTELIGENTE DE CEP ---
                    col_cep_input, col_cep_btn = st.columns([3, 1])
                    with col_cep_input:
                        c_cep = st.text_input("CEP da Obra (somente números) *")
                    with col_cep_btn:
                        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                        if st.button("🔍 Buscar", key="btn_busca_cep", type="secondary", use_container_width=True):
                            cep_limpo = re.sub(r'\D', '', c_cep)
                            if len(cep_limpo) == 8:
                                with st.spinner("Buscando Endereço..."):
                                    try:
                                        res = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=5)
                                        if res.status_code == 200:
                                            dados = res.json()
                                            if "erro" not in dados:
                                                endereco_formatado = f"{dados.get('logradouro', '')}, {dados.get('bairro', '')} - {dados.get('localidade', '')}/{dados.get('uf', '')}"
                                                st.session_state['end_obra_temp'] = endereco_formatado
                                            else:
                                                st.error("CEP inexistente.")
                                        else:
                                            st.error("Erro na consulta.")
                                    except:
                                        st.error("Falha ao conectar com o ViaCEP.")
                            else:
                                st.warning("Digite os 8 números do CEP.")
                                
                    c_obra = st.text_input("Endereço Completo da Obra *", value=st.session_state.get('end_obra_temp', ''))
                        
                    c_modelos = st.multiselect("Modelos de Estaca *", lista_modelos_geral)
                    
                    metragens_contratadas = {}
                    if c_modelos:
                        st.info("Preencha a metragem total prevista para cada modelo:")
                        cols_metragem = st.columns(len(c_modelos))
                        for i, mod in enumerate(c_modelos):
                            with cols_metragem[i % len(cols_metragem)]:
                                metragens_contratadas[mod] = st.number_input(f"Total {mod} (m)", min_value=0, step=10, key=f"met_{mod}")
                    
                    c_comprimentos = st.multiselect("Comprimentos de Fábrica Permitidos (m) *", lista_comprimentos_geral)
                    
                    st.markdown("**3. Selecione a Transportadora**")
                    if lista_transportadoras_geral:
                        c_transportadora = st.selectbox("Transportadoras Registadas *", [""] + lista_transportadoras_geral)
                    else:
                        c_transportadora = st.selectbox("Transportadoras Registadas *", ["Nenhuma cadastrada"])
                        
                    # ✅ EXIBE A MENSAGEM SALVA NA MEMÓRIA APÓS O REINÍCIO
                    if 'msg_transp' in st.session_state:
                        st.success(st.session_state['msg_transp'])
                        del st.session_state['msg_transp']
                        
                    with st.expander("Adicionar Nova Transportadora"):
                        with st.form("form_nova_transp"):
                            st.write("Cadastre os dados da nova transportadora:")
                            t_nome = st.text_input("Nome da Transportadora *")
                            col_t1, col_t2 = st.columns(2)
                            with col_t1:
                                t_cnpj = st.text_input("CNPJ")
                                t_tel = st.text_input("Telefone")
                            with col_t2:
                                t_end = st.text_input("Endereço Completo")
                                t_email = st.text_input("Email")
                                
                            btn_add_transp = st.form_submit_button("Salvar Transportadora")
                            
                            if btn_add_transp:
                                if t_nome:
                                    aba_transportadoras.append_row([t_nome, t_cnpj, t_end, t_tel, t_email])
                                    # ✅ LIMPA APENAS O CACHE DA FUNÇÃO DE LISTAS
                                    buscar_cadastros_listas.clear() 
                                    # ✅ SALVA A MENSAGEM NA MEMÓRIA ANTES DO RERUN
                                    st.session_state['msg_transp'] = f"✅ Transportadora '{t_nome}' cadastrada com sucesso!"
                                    st.rerun()
                                else:
                                    st.warning("⚠️ O Nome da Transportadora é obrigatório.")

                    st.write("")
                    if st.button("Gerar Código e Salvar Contrato", type="primary"):
                        if c_cliente == "" or c_obra == "" or len(c_modelos) == 0 or len(c_comprimentos) == 0 or c_cnpj == "" or c_transportadora == "" or c_transportadora == "Nenhuma cadastrada":
                            st.warning("⚠️ Preencha todos os campos, selecione os modelos e a transportadora.")
                        else:
                            ano_atual = str(datetime.now().year)
                            if not df_contratos.empty:
                                codigos_ano = [cod for cod in df_contratos['Codigo'].tolist() if str(cod).startswith(ano_atual)]
                                if codigos_ano:
                                    max_seq = max([int(c[4:]) for c in codigos_ano if len(c) == 8 and c[4:].isdigit()])
                                    novo_codigo = f"{ano_atual}{(max_seq + 1):04d}"
                                else:
                                    novo_codigo = f"{ano_atual}0001"
                            else:
                                novo_codigo = f"{ano_atual}0001"
                            
                            itens_dict = {
                                "cnpj": c_cnpj,
                                "transportadora": c_transportadora,
                                "modelos": c_modelos,
                                "comprimentos": c_comprimentos,
                                "metragens": metragens_contratadas,
                                "senha": "" 
                            }
                            itens_json = json.dumps(itens_dict)
                            
                            with st.spinner("A guardar contrato..."):
                                aba_contratos.append_row([novo_codigo, c_cliente, c_obra, itens_json])
                                st.cache_data.clear() 
                                st.success(f"✅ Contrato criado! O código gerado é: **{novo_codigo}** (Envie este código ao cliente para que ele crie a senha no 'Primeiro Acesso')")

                with col_cad2:
                    st.subheader("📂 Consulta de Saldos e Consumo")
                    if not df_contratos.empty:
                        lista_contratos = df_contratos['Codigo'] + " - " + df_contratos['Cliente'] + " (" + df_contratos['Obra'] + ")"
                        contrato_selecionado = st.selectbox("Selecione a Obra para ver o Saldo:", [""] + lista_contratos.tolist())
                        
                        if contrato_selecionado != "":
                            cod_selecionado = contrato_selecionado.split(" - ")[0]
                            info_contrato = df_contratos[df_contratos['Codigo'] == cod_selecionado].iloc[0]
                            itens_contrato = json.loads(info_contrato['Itens'])
                            metragens = itens_contrato.get('metragens', {})
                            
                            saldos, consumos = calcular_saldos(cod_selecionado, metragens)
                            
                            status_senha = "🟢 Criada pelo Cliente" if itens_contrato.get('senha', '') != "" else "🔴 Aguardando 1º Acesso"
                            st.markdown(f"**Obra: {info_contrato['Obra']}** | Status da Senha: {status_senha}")
                            
                            for mod, total_contratado in metragens.items():
                                saldo_atual = saldos.get(mod, 0)
                                consumido_atual = consumos.get(mod, 0)
                                
                                st.info(f"**Estaca {mod}:** {f'{total_contratado:,.0f}'.replace(',', '.')} m contratados")
                                col_s1, col_s2 = st.columns(2)
                                col_s1.metric(label="Saldo Disponível", value=f"{f'{saldo_atual:,.0f}'.replace(',', '.')} m")
                                col_s2.metric(label="Já Entregue", value=f"{f'{consumido_atual:,.0f}'.replace(',', '.')} m", delta=f"{(consumido_atual/total_contratado)*100:.1f}%" if total_contratado > 0 else "0%", delta_color="off")
                                st.write("")
                    else:
                        st.info("Nenhum contrato registado.")

        except Exception as e:
            st.error(f"Erro ao carregar o painel: {e}")
            
    st.stop() 

# ==========================================
# ÁREA DO CLIENTE (MÚLTIPLAS CARRETAS E HISTÓRICO 🚚🕰️)
# ==========================================

PESO_POR_METRO = {
    "17x17": 70, "ICP360": 130, "ETR229": 66, "ETR269": 90, "ETR360": 137, 
    "ETR406": 159, "ETR445": 201, "ETR525": 250, "ETR605": 325, "ETR707": 400, "ETR809": 530
}
PESO_PADRAO = 100 

def gerar_recibo_frota_pdf(data_atual, solicitante, cliente, obra, obs, carretas_info):
    
    # Criamos uma classe personalizada para injetar Cabeçalho e Rodapé em todas as páginas
    class PDFRecibo(FPDF):
        def header(self):
            # 1. Injeta a Logo da FOÁ no canto superior esquerdo
            try:
                self.image("FOÁ ENGENHARIA.png", 10, 8, 35)
            except:
                pass # Se a imagem não for encontrada no servidor, ele gera o PDF sem quebrar
            
            # 2. Título Centralizado com o Azul Corporativo (#044589 -> RGB: 4, 69, 137)
            self.set_font("helvetica", "B", 16)
            self.set_text_color(4, 69, 137) 
            self.cell(0, 15, "Comprovante de Pedido de Estacas", ln=True, align="C")
            
            # Espaçamento entre o cabeçalho e o texto principal
            self.ln(10) 
            self.set_text_color(0, 0, 0) # Volta a cor da letra para preto

        def footer(self):
            # 3. Rodapé posicionado a 1,5cm do final da página
            self.set_y(-15)
            self.set_font("helvetica", "I", 10)
            self.set_text_color(100, 100, 100) # Cinza escuro elegante
            # Endereço da Sede da FOÁ
            self.cell(0, 10, "Avenida Buriti, 3185 - Feital - Pindamonhangaba - SP", align="C")

    # Inicia a criação do PDF usando a nossa regra personalizada acima
    pdf = PDFRecibo()
    pdf.add_page()
    
    # --- CONTEÚDO DO PDF ---
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 8, f"Data da Solicitacao: {data_atual}", ln=True)
    pdf.cell(0, 8, f"Solicitante: {solicitante}", ln=True)
    pdf.cell(0, 8, f"Cliente/Empresa: {cliente}", ln=True)
    pdf.cell(0, 8, f"Obra/Local: {obra}", ln=True)
    if obs:
        pdf.cell(0, 8, f"Observacoes Globais: {obs}", ln=True)
    
    for idx, c_info in enumerate(carretas_info):
        pdf.ln(5)
        pdf.set_font("helvetica", "B", 14)
        pdf.cell(0, 10, f"Carreta {idx+1} (ID do Pedido: {c_info['id']})", ln=True)
        pdf.set_font("helvetica", "", 11)
        pdf.cell(0, 8, f"Veiculo: {c_info['veiculo']} | Data Desejada: {c_info['data']}", ln=True)
        
        for item in c_info['itens']:
            qtd_formatada = f"{item['Quantidade']:02d}"
            id_item = item.get('ID_Item', '-')
            modelo = item['Modelo']
            comprimento = item['Comprimento']
            metragem_str = f"{item['Metragem Total']:,.0f}".replace(',', '.')
            
            texto_item = f"Item: {id_item} | Quantidade: {qtd_formatada} Estacas {modelo} ({comprimento}m) | Total: {metragem_str}m"
            pdf.cell(0, 8, texto_item, ln=True)
            
        peso_total = sum(item['Peso (kg)'] for item in c_info['itens'])
        pdf.set_font("helvetica", "I", 11) 
        pdf.cell(0, 8, f"Peso total desta carga: {f'{peso_total:,.0f}'.replace(',', '.')} kg", ln=True)
        
    return pdf.output(dest="S").encode("latin-1")


if 'pdf_pronto' in st.session_state:
    st.title("✅ Pedidos Concluídos com Sucesso!")
    st.success("As suas solicitações de carga foram recebidas pela logística.")
    
    nome_cliente = st.session_state['cliente_nome']
    data_arquivo = datetime.now(timezone(timedelta(hours=-3))).strftime("%d-%m-%Y")
    nome_pdf_personalizado = f"Pedido_Estacas {nome_cliente} - {data_arquivo}.pdf"
    
    st.download_button("📄 Baixar Comprovante Consolidado (PDF)", data=st.session_state['pdf_pronto'], file_name=nome_pdf_personalizado, mime="application/pdf", type="primary")
    
    st.divider()
    if st.button("🔄 Fazer Nova Solicitação ou Ver Histórico"):
        del st.session_state['pdf_pronto']
        st.session_state['carrinhos'] = {}
        st.rerun()
    st.stop()
# ==========================================
# CABEÇALHO DA ÁREA DO CLIENTE
# ==========================================
col_logo_cli, col_titulo_cli, col_botoes_cli = st.columns([2, 5, 2])

with col_logo_cli:
    try:
        # Puxa a mesma imagem e usa o tamanho adaptável da coluna (igual ao admin)
        st.image("FOÁ ENGENHARIA.png", use_container_width=True)
    except:
        st.warning("⚠️ Imagem FOÁ ENGENHARIA.png não encontrada.")
        
with col_titulo_cli:
    st.write("") # Espaçamento para alinhar verticalmente
    st.markdown("## 📦 Portal do Cliente")
    
with col_botoes_cli:
    st.write("") # Espaçamento
    # Adicionei uma 'key' para evitar conflito com o botão de sair do admin
    if st.button("🚪 Sair / Logout", key="btn_sair_cliente"):
        st.session_state['autenticado'] = False
        st.session_state['perfil'] = ""
        st.rerun()

st.divider()

tab_novo_pedido, tab_historico = st.tabs(["🚀 Nova Solicitação", "🕰️ Histórico de Pedidos"])

# ==========================================
# ABA 1: FAZER NOVO PEDIDO
# ==========================================
with tab_novo_pedido:
    st.subheader("1. Planejamento da Frota")
    num_carretas = st.number_input("Quantas carretas deseja solicitar neste pedido?", min_value=1, max_value=10, value=1, step=1)

    for i in range(int(num_carretas)):
        if i not in st.session_state['carrinhos']:
            st.session_state['carrinhos'][i] = []

    st.divider()

    st.subheader("2. Dados Gerais")
    solicitante = st.text_input("Nome do Solicitante (Seu Nome) *")

    col_a1, col_a2, col_a3 = st.columns(3)
    with col_a1:
        cliente_empresa = st.text_input("Cliente / Empresa *", value=st.session_state['cliente_nome'], disabled=True)
    with col_a2:
        cnpj_cliente = st.text_input("CNPJ *", value=st.session_state.get('cnpj', ''), disabled=True)
    with col_a3:
        obra_local = st.text_input("Obra / Local *", value=st.session_state['obra_nome'], disabled=True)

    st.info(f"🚚 **Transportadora Contratada:** {st.session_state.get('transportadora', 'Não informada')}")
    observacoes = st.text_area("Observações Gerais (Opcional)")

    st.divider() 

    saldos_banco, _ = calcular_saldos(st.session_state['codigo_contrato'], st.session_state['metragens_contratadas'])

    for i in range(int(num_carretas)):
        for item in st.session_state['carrinhos'].get(i, []):
            mod_carrinho = item['Modelo']
            met_carrinho = item['Metragem Total']
            if mod_carrinho in saldos_banco:
                saldos_banco[mod_carrinho] -= met_carrinho

    st.subheader("3. Gestão de Cargas e Saldo")
    
    cols_saldo_cliente = st.columns(len(st.session_state['modelos_permitidos']))
    for i, mod in enumerate(st.session_state['modelos_permitidos']):
        saldo_atual = saldos_banco.get(mod, 0)
        saldo_formatado = f"{saldo_atual:,.0f}".replace(",", ".")
        
        card_html = f"""
        <div style="background-color: #f0f8ff; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #cce5ff; margin-bottom: 15px;">
            <p style="margin: 0; font-size: 14px; color: #555;">Saldo Restante: <strong>{mod}</strong></p>
            <h3 style="margin: 5px 0 0 0; color: #0056b3;">{saldo_formatado} m</h3>
        </div>
        """
        with cols_saldo_cliente[i % len(cols_saldo_cliente)]:
            st.markdown(card_html, unsafe_allow_html=True)

    abas_carretas = st.tabs([f"🚚 Carreta {i+1}" for i in range(int(num_carretas))])
    veiculos_selecionados = {}
    datas_selecionadas = {}

    data_minima = datetime.now().date() + timedelta(days=2)

    for i, aba in enumerate(abas_carretas):
        with aba:
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                veiculos_selecionados[i] = st.radio("Tipo de Veículo:", ["Carreta Munk (23.500 kg)", "Prancha (26.000 kg)"], key=f"veiculo_{i}")
            with col_v2:
                datas_selecionadas[i] = st.date_input("Data Desejada:", min_value=data_minima, value=data_minima, key=f"data_{i}", format="DD/MM/YYYY")
                
            st.write("**Adicionar Estacas a esta carga:**")
            
            # ✅ Transformamos em 4 colunas para o botão ficar na mesma linha
            col_b1, col_b2, col_b3, col_b4 = st.columns([3, 2, 2, 3])
            
            with col_b1:
                modelo = st.selectbox("Modelo da Estaca", st.session_state['modelos_permitidos'], key=f"mod_{i}")
            with col_b2:
                comprimento = st.selectbox("Comprimento (m)", st.session_state['comprimentos_permitidos'], key=f"comp_{i}")
            with col_b3:
                quantidade = st.number_input("Quantidade", min_value=1, step=1, key=f"qtd_{i}")
            with col_b4:
                # Espaçamento em HTML para alinhar o botão perfeitamente com as caixas de texto
                st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True) 
                
                # Transformamos em type="primary" e usamos o ícone nativo
                if st.button("Adicionar", icon=":material/add_circle:", key=f"btn_add_{i}", type="primary", use_container_width=True):
                    
                    metragem_total = quantidade * int(comprimento)
                    saldo_disponivel = saldos_banco.get(modelo, 0)
                    
                    if metragem_total > saldo_disponivel:
                        st.error(f"⚠️ Saldo Insuficiente! Faltam metros de {modelo} no seu contrato global para esta adição.")
                    else:
                        peso_linear = PESO_POR_METRO.get(modelo, PESO_PADRAO)
                        peso_total_item = metragem_total * peso_linear
                        st.session_state['carrinhos'][i].append({"Modelo": modelo, "Comprimento": comprimento, "Quantidade": quantidade, "Metragem Total": metragem_total, "Peso (kg)": peso_total_item})
                        st.rerun() 

            peso_total_carrinho = sum(item['Peso (kg)'] for item in st.session_state['carrinhos'][i])
            capacidade_maxima = 23500 if "Munk" in veiculos_selecionados[i] else 26000
            
            st.write("---")
            if len(st.session_state['carrinhos'][i]) > 0:
                for j, item in enumerate(st.session_state['carrinhos'][i]):
                    c_texto, c_botao = st.columns([5, 1])
                    with c_texto:
                        met_str = f"{item['Metragem Total']:,.0f}".replace(",", ".")
                        peso_str = f"{item['Peso (kg)']:,.0f}".replace(",", ".")
                        st.info(f"**{item['Quantidade']}x {item['Modelo']}** ({item['Comprimento']}m) | Metragem: {met_str} m | {peso_str} kg")
                    with c_botao:
                        if st.button("🗑️", key=f"exc_{i}_{j}"):
                            st.session_state['carrinhos'][i].pop(j)
                            st.rerun() 
                
                st.metric(label=f"Ocupação de Peso", value=f"{f'{peso_total_carrinho:,.0f}'.replace(',', '.')} kg", delta=f"Capacidade: {f'{capacidade_maxima:,.0f}'.replace(',', '.')} kg", delta_color="off")
                percentual_carga = min(peso_total_carrinho / capacidade_maxima, 1.0)
                
                if peso_total_carrinho > capacidade_maxima:
                    st.error("⚠️ Excesso de Carga nesta carreta!")
                    st.progress(1.0)
                else:
                    st.progress(percentual_carga)
            else:
                st.write("Esta carreta está vazia.")

    st.divider()

    st.subheader("4. Finalização")
    
    total_itens_geral = sum([len(st.session_state['carrinhos'][i]) for i in range(int(num_carretas))])
    
    if total_itens_geral > 0:
        with st.expander("🔍 Pré-Visualizar e Confirmar Pedido", expanded=False):
            st.markdown("### Resumo da Solicitação")
            st.write(f"**Solicitante:** {solicitante}")
            st.write(f"**Obra:** {obra_local} | **Transportadora:** {st.session_state.get('transportadora', '')}")
            st.markdown("---")
            
            for i in range(int(num_carretas)):
                if len(st.session_state['carrinhos'][i]) > 0:
                    data_entrega = datas_selecionadas[i].strftime("%d/%m/%Y")
                    st.markdown(f"#### 🚚 Carreta {i+1} ({veiculos_selecionados[i]} - Para dia {data_entrega})")
                    for item in st.session_state['carrinhos'][i]:
                        met_str = f"{item['Metragem Total']:,.0f}".replace(",", ".")
                        st.write(f"- {item['Quantidade']} unidades de **{item['Modelo']}** ({item['Comprimento']}m) ➔ Total: {met_str} metros")
            
            st.write("")
            st.info("Por favor, confira as quantidades acima. Se estiver tudo correto, clique no botão abaixo para concluir o pedido.")
            
            if st.button("🚀 Confirmar e Enviar Pedidos para a Fábrica", type="primary"):
                carretas_vazias = [i+1 for i in range(int(num_carretas)) if len(st.session_state['carrinhos'][i]) == 0]
                
                if solicitante == "":
                    st.warning("⚠️ O campo Nome do Solicitante ficou vazio no formulário acima.")
                elif carretas_vazias:
                    st.warning(f"⚠️ As carretas {carretas_vazias} estão vazias. Volte e remova-as ou adicione estacas.")
                else:
                    with st.spinner("A processar a inteligência de IDs e gerar PDF..."):
                        fuso_br = timezone(timedelta(hours=-3))
                        data_atual = datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")
                        
                        codigo_contrato = st.session_state['codigo_contrato']
                        dados_p, _, _ = carregar_dados_planilhas()
                        df_p = pd.DataFrame(dados_p[1:], columns=dados_p[0]) if len(dados_p) > 1 else pd.DataFrame()
                        
                        seq_inicial = 1
                        if not df_p.empty and codigo_contrato in df_p[df_p.columns[9]].values:
                            pedidos_existentes = df_p[df_p[df_p.columns[9]] == codigo_contrato][df_p.columns[0]].tolist()
                            seqs = []
                            for p_id in pedidos_existentes:
                                if str(p_id).startswith(codigo_contrato):
                                    try:
                                        seqs.append(int(p_id[-3:]))
                                    except:
                                        pass
                            if seqs:
                                seq_inicial = max(seqs) + 1
                        
                        carretas_pdf_info = []
                        linhas_pedidos_insert = []
                        linhas_itens_insert = []
                        
                        for i in range(int(num_carretas)):
                            id_pedido = f"{codigo_contrato}{seq_inicial + i:03d}"
                            veiculo_str = veiculos_selecionados[i]
                            data_desejada_str = datas_selecionadas[i].strftime("%d/%m/%Y")
                            carrinho_atual = st.session_state['carrinhos'][i]
                            
                            linhas_pedidos_insert.append([id_pedido, data_atual, solicitante, cliente_empresa, obra_local, data_desejada_str, veiculo_str, observacoes, "Pendente", codigo_contrato])
                            
                            for idx_item, item in enumerate(carrinho_atual):
                                letra_item = chr(65 + idx_item)
                                id_item = f"{id_pedido}{letra_item}"
                                item['ID_Item'] = id_item
                                linhas_itens_insert.append([id_item, id_pedido, item["Modelo"], item["Comprimento"], item["Quantidade"], item["Metragem Total"], item["Peso (kg)"]])
                                
                            carretas_pdf_info.append({
                                'id': id_pedido,
                                'veiculo': veiculo_str,
                                'data': data_desejada_str,
                                'itens': carrinho_atual
                            })
                        
                        try:
                            aba_pedidos.append_rows(linhas_pedidos_insert)
                            aba_itens.append_rows(linhas_itens_insert)
                            pdf_bytes = gerar_recibo_frota_pdf(data_atual, solicitante, cliente_empresa, obra_local, observacoes, carretas_pdf_info)
                            st.cache_data.clear() 
                            st.session_state['pdf_pronto'] = pdf_bytes
                            st.session_state['carrinhos'] = {} 
                            st.rerun() 
                        except Exception as e:
                            st.error(f"❌ Ocorreu um erro ao guardar: {e}")
    else:
        st.info("Adicione estacas aos veículos acima para liberar a finalização do pedido.")

# ==========================================
# ABA 2: HISTÓRICO DE PEDIDOS (COM PAINÉIS EXPANSÍVEIS)
# ==========================================
with tab_historico:
    st.subheader("🕰️ Seus Pedidos Anteriores")
    st.markdown("Clique sobre um pedido para ver os detalhes da carga solicitada.")
    
    dados_pedidos, dados_itens, _ = carregar_dados_planilhas()
    df_p = pd.DataFrame(dados_pedidos[1:], columns=dados_pedidos[0]) if len(dados_pedidos) > 1 else pd.DataFrame()
    df_i = pd.DataFrame(dados_itens[1:], columns=dados_itens[0]) if len(dados_itens) > 1 else pd.DataFrame()

    if not df_p.empty and len(df_p.columns) >= 10:
        meus_pedidos = df_p[df_p[df_p.columns[9]] == st.session_state['codigo_contrato']]

        if not meus_pedidos.empty:
            meus_pedidos_recentes = meus_pedidos.iloc[::-1]

            for _, row_pedido in meus_pedidos_recentes.iterrows():
                id_pedido = row_pedido[df_p.columns[0]]
                data_solic = row_pedido[df_p.columns[1]]
                data_desej = row_pedido[df_p.columns[5]]
                veiculo = row_pedido[df_p.columns[6]]
                status_atual = row_pedido[df_p.columns[8]]
                
                emoji = "🔵"
                if status_atual == "Entregue": emoji = "🟢"
                elif status_atual == "Cancelado": emoji = "🔴"
                elif status_atual == "Em Transporte": emoji = "🟠"
                
                titulo_card = f"{emoji} Pedido: {id_pedido} | Solicitado em: {data_solic} | Status: {status_atual}"
                
                with st.expander(titulo_card):
                    st.info(f"**Veículo:** {veiculo} | **Data Desejada para Entrega:** {data_desej}")

                    if not df_i.empty:
                        itens_do_pedido = df_i[df_i[df_i.columns[1]] == id_pedido]
                        if not itens_do_pedido.empty:
                            colunas_mostrar = [df_i.columns[0], df_i.columns[2], df_i.columns[3], df_i.columns[4], df_i.columns[5], df_i.columns[6]]
                            df_mostrar = itens_do_pedido[colunas_mostrar].copy()
                            df_mostrar.columns = ["Cód. Item", "Modelo", "Comprimento (m)", "Quantidade", "Total (m)", "Peso (kg)"]
                            st.dataframe(df_mostrar, use_container_width=True, hide_index=True)
                        else:
                            st.warning("Nenhum item encontrado para este pedido.")
        else:
            st.info("Você ainda não possui histórico de cargas solicitadas para este contrato.")
    else:
        st.info("O sistema ainda não possui pedidos registados.")