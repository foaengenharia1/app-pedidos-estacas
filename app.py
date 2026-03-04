import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import uuid
from datetime import datetime, timedelta, timezone # <-- Fuso horário adicionado aqui!
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
# ÁREA DO ADMINISTRADOR
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
                
                tab_visao, tab_gestao = st.tabs(["📊 Visão Estratégica", "📋 Gestão e Status"])
                
                # --- ABA 1: VISÃO ESTRATÉGICA ---
                with tab_visao:
                    st.subheader("Planejamento de Cargas e Produção")
                    
                    col_data_desejada = df_pedidos.columns[5]
                    usar_filtro = st.toggle("Filtrar por uma data específica", value=True)
                    
                    if usar_filtro:
                        data_selecionada = st.date_input("📅 Selecione a Data para planejar o carregamento:", format="DD/MM/YYYY")
                        data_str = data_selecionada.strftime("%d/%m/%Y")
                        df_pedidos_filtrado = df_pedidos[df_pedidos[col_data_desejada] == data_str]
                        data_exibicao = data_str
                    else:
                        df_pedidos_filtrado = df_pedidos
                        data_exibicao = "Todas as Datas"
                        
                    st.write("") 
                    
                    if not df_pedidos_filtrado.empty:
                        col_m1, col_m2 = st.columns(2)
                        col_m1.metric("Total de Pedidos (Cargas)", len(df_pedidos_filtrado))
                        col_m2.metric("Data Analisada", data_exibicao)
                        
                        st.divider()
                        
                        col_graf1, col_graf2 = st.columns(2)
                        
                        with col_graf1:
                            st.markdown("**🚚 Previsão de Veículos por Cliente**")
                            col_cliente = df_pedidos.columns[3]
                            col_obra = df_pedidos.columns[4]
                            col_veiculo = df_pedidos.columns[6]
                            
                            cargas_por_cliente = df_pedidos_filtrado.groupby([col_cliente, col_obra, col_veiculo]).size().reset_index(name='Quantidade de Veículos')
                            cargas_por_cliente = cargas_por_cliente.rename(columns={col_cliente: 'Cliente', col_obra: 'Obra', col_veiculo: 'Tipo de Veículo'})
                            st.dataframe(cargas_por_cliente, hide_index=True, use_container_width=True)
                            
                        with col_graf2:
                            st.markdown("**🏗️ Total de Estacas a Produzir/Carregar**")
                            if not df_itens.empty:
                                col_id_pedido_ped = df_pedidos.columns[0]
                                col_id_pedido_item = df_itens.columns[1]
                                col_modelo = df_itens.columns[2]
                                col_comprimento = df_itens.columns[3]
                                col_quantidade = df_itens.columns[4]
                                col_metragem = df_itens.columns[5] 
                                
                                ids_filtrados = df_pedidos_filtrado[col_id_pedido_ped].tolist()
                                itens_filtrados = df_itens[df_itens[col_id_pedido_item].isin(ids_filtrados)].copy()
                                
                                if not itens_filtrados.empty:
                                    itens_filtrados[col_quantidade] = pd.to_numeric(itens_filtrados[col_quantidade], errors='coerce').fillna(0)
                                    itens_filtrados[col_metragem] = pd.to_numeric(itens_filtrados[col_metragem], errors='coerce').fillna(0)
                                    
                                    estacas_por_modelo = itens_filtrados.groupby([col_modelo, col_comprimento]).agg({col_quantidade: 'sum', col_metragem: 'sum'}).reset_index()
                                    estacas_por_modelo = estacas_por_modelo.rename(columns={col_modelo: 'Estaca', col_comprimento: 'Comprimento (m)', col_quantidade: 'Quantidade (Unid.)', col_metragem: 'Metragem Total'})
                                    st.dataframe(estacas_por_modelo, hide_index=True, use_container_width=True)
                                else:
                                    st.info("Nenhum item associado a estes pedidos.")
                    else:
                        st.warning("⚠️ Nenhum pedido encontrado para a data selecionada.")

                # --- ABA 2: GESTÃO E STATUS (AGORA COM VISUALIZAÇÃO DE ITENS) ---
                with tab_gestao:
                    df_pedidos_inverso = df_pedidos.iloc[::-1]
                    st.dataframe(df_pedidos_inverso, use_container_width=True, hide_index=True)
                    
                    st.divider()
                    st.subheader("🔍 Detalhes e Atualização de Status")
                    
                    lista_ids = [str(id) for id in df_pedidos[df_pedidos.columns[0]].tolist() if str(id).strip() != ""]
                    
                    pedido_selecionado = st.selectbox("Selecione o ID do Pedido para visualizar os detalhes:", [""] + lista_ids)
                    
                    if pedido_selecionado != "":
                        # --- NOVO: MOSTRA OS DETALHES DO PEDIDO SELECIONADO ---
                        info_pedido = df_pedidos[df_pedidos[df_pedidos.columns[0]] == pedido_selecionado].iloc[0]
                        
                        st.markdown(f"### 📦 Itens do Pedido: **{pedido_selecionado}**")
                        st.info(f"**Cliente:** {info_pedido[df_pedidos.columns[3]]} | **Obra:** {info_pedido[df_pedidos.columns[4]]} | **Veículo:** {info_pedido[df_pedidos.columns[6]]}")
                        
                        if not df_itens.empty:
                            itens_do_pedido = df_itens[df_itens[df_itens.columns[1]] == pedido_selecionado]
                            if not itens_do_pedido.empty:
                                # Filtra apenas as colunas amigáveis para mostrar na tela
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
                            # Já deixa selecionado o status que está na planilha hoje
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
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, f"ID do Pedido: {id_pedido}", ln=True)
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 8, f"Data da Solicitacao: {data}", ln=True)
    pdf.cell(0, 8, f"Solicitante: {solicitante}", ln=True)
    pdf.cell(0, 8, f"Cliente/Empresa: {cliente}", ln=True)
    pdf.cell(0, 8, f"Obra/Local: {obra}", ln=True)
    pdf.cell(0, 8, f"Data Desejada: {data_desejada}", ln=True)
    pdf.cell(0, 8, f"Veiculo Selecionado: {veiculo}", ln=True)
    if obs:
        pdf.cell(0, 8, f"Observacoes: {obs}", ln=True)
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 10, "Itens Solicitados:", ln=True)
    pdf.set_font("helvetica", "", 12)
    for item in carrinho:
        texto_item = f"- {item['Quantidade']}x modelo {item['Modelo']} ({item['Comprimento']}m) | Metragem: {item['Metragem Total']}m | Peso: {item['Peso (kg)']:,.0f} kg"
        pdf.cell(0, 8, texto_item, ln=True)
    pdf.ln(5) 
    pdf.set_font("helvetica", "B", 12) 
    peso_total = sum(item['Peso (kg)'] for item in carrinho)
    pdf.cell(0, 10, f"Peso total da carga: {peso_total:,.0f} kg.", ln=True)
    return bytes(pdf.output())

if 'carrinho' not in st.session_state:
    st.session_state['carrinho'] = []

if 'pdf_pronto' in st.session_state:
    st.title("✅ Pedido Concluído!")
    st.success("Seu pedido foi recebido com sucesso pela nossa equipa de logística.")
    st.download_button("📄 Baixar Comprovante em PDF", data=st.session_state['pdf_pronto'], file_name=f"Pedido_{st.session_state['id_pedido']}.pdf", mime="application/pdf", type="primary")
    st.divider()
    if st.button("🔄 Fazer Novo Pedido"):
        del st.session_state['pdf_pronto']
        del st.session_state['id_pedido']
        st.rerun()
    st.stop() 

try:
    st.image("logo.png", width=200)
except:
    pass

col_sair1, col_sair2 = st.columns([10, 2])
with col_sair2:
    if st.button("Sair"):
        st.session_state['autenticado'] = False
        st.session_state['perfil'] = ""
        st.rerun()

st.title("📦 Solicitação de Estacas")

st.subheader("1. Logística e Transporte")
tipo_veiculo = st.radio("Escolha o tipo de transporte desejado:", ["Carreta Munk (Capacidade: 23.500 kg)", "Prancha (Capacidade: 26.000 kg)"], horizontal=True)
capacidade_maxima = 23500 if "Munk" in tipo_veiculo else 26000

st.divider()

st.subheader("2. Dados do Cliente e Entrega")
col_a1, col_a2 = st.columns(2)
with col_a1:
    solicitante = st.text_input("Nome do Solicitante *")
    cliente_empresa = st.text_input("Cliente / Empresa *")
with col_a2:
    obra_local = st.text_input("Obra / Local de Entrega *")
    data_minima = datetime.now().date() + timedelta(days=2)
    data_desejada = st.date_input("Data Desejada para Entrega *", min_value=data_minima, value=data_minima, format="DD/MM/YYYY", help="Prazo mínimo de 48h.")

observacoes = st.text_area("Observações Gerais (Opcional)")

st.divider() 

st.subheader("3. Adicionar Estacas ao Pedido")
col_b1, col_b2, col_b3 = st.columns(3)
with col_b1:
    modelo = st.selectbox("Modelo da Estaca", lista_modelos)
with col_b2:
    comprimento = st.selectbox("Comprimento (Metros)", lista_comprimentos)
with col_b3:
    quantidade = st.number_input("Quantidade", min_value=1, step=1)

if st.button("➕ Adicionar ao Pedido"):
    metragem_total = quantidade * int(comprimento)
    peso_linear = PESO_POR_METRO.get(modelo, PESO_PADRAO)
    peso_total_item = metragem_total * peso_linear
    st.session_state['carrinho'].append({"Modelo": modelo, "Comprimento": comprimento, "Quantidade": quantidade, "Metragem Total": metragem_total, "Peso (kg)": peso_total_item})
    st.success(f"{quantidade}x {modelo} adicionado(s)! Peso estimado: {peso_total_item:,.0f} kg")

st.divider()

st.subheader("4. Resumo da Carga")
peso_total_carrinho = sum(item['Peso (kg)'] for item in st.session_state['carrinho'])

if len(st.session_state['carrinho']) > 0:
    col_c1, col_c2 = st.columns([2, 1])
    with col_c1:
        st.write("**Itens no pedido:**")
        for i, item in enumerate(st.session_state['carrinho']):
            c_texto, c_botao = st.columns([4, 1])
            with c_texto:
                st.info(f"**{item['Quantidade']}x {item['Modelo']}** ({item['Comprimento']}m) | {item['Peso (kg)']:,.0f} kg")
            with c_botao:
                if st.button("🗑️", key=f"excluir_{i}", help="Remover este item"):
                    st.session_state['carrinho'].pop(i)
                    st.rerun() 
        
    with col_c2:
        veiculo_nome = "Munk" if "Munk" in tipo_veiculo else "Prancha"
        st.metric(label=f"Peso no Veículo ({veiculo_nome})", value=f"{peso_total_carrinho:,.0f} kg", delta=f"Capacidade: {capacidade_maxima:,.0f} kg", delta_color="off")
        percentual_carga = min(peso_total_carrinho / capacidade_maxima, 1.0)
        
        if peso_total_carrinho > capacidade_maxima:
            st.error("⚠️ Excesso de Carga! O peso ultrapassa a capacidade do veículo.")
            st.progress(1.0)
        else:
            st.progress(percentual_carga)
    
    st.write("") 
    
    if st.button("🚀 Finalizar e Enviar Pedido", type="primary"):
        if solicitante == "" or cliente_empresa == "" or obra_local == "":
            st.warning("⚠️ Por favor, preencha os campos com asterisco (*) antes de enviar.")
        else:
            with st.spinner("A enviar pedido e a gerar PDF..."):
                id_pedido = str(uuid.uuid4())[:8].upper()
                
                # --- CORREÇÃO DO FUSO HORÁRIO APLICADA AQUI (UTC-3) ---
                fuso_br = timezone(timedelta(hours=-3))
                data_atual = datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")
                
                data_desejada_str = data_desejada.strftime("%d/%m/%Y")
                
                try:
                    linha_pedido = [id_pedido, data_atual, solicitante, cliente_empresa, obra_local, data_desejada_str, tipo_veiculo, observacoes, "Pendente"]
                    aba_pedidos.append_row(linha_pedido)
                    
                    para_inserir = []
                    for item in st.session_state['carrinho']:
                        id_item = str(uuid.uuid4())[:8].upper()
                        linha_item = [id_item, id_pedido, item["Modelo"], item["Comprimento"], item["Quantidade"], item["Metragem Total"], item["Peso (kg)"]]
                        para_inserir.append(linha_item)
                    aba_itens.append_rows(para_inserir)
                    
                    pdf_bytes = gerar_recibo_pdf(id_pedido, data_atual, solicitante, cliente_empresa, obra_local, data_desejada_str, tipo_veiculo, observacoes, st.session_state['carrinho'])
                    
                    st.session_state['pdf_pronto'] = pdf_bytes
                    st.session_state['id_pedido'] = id_pedido
                    st.session_state['carrinho'] = [] 
                    st.rerun() 
                    
                except Exception as e:
                    st.error(f"❌ Ocorreu um erro ao guardar: {e}")
else:
    st.info("O seu pedido ainda está vazio. Adicione estacas acima.")