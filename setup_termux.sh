#!/bin/bash
# SETUP TERMUX PARA PROBE MONITOR - FIREBASE

set -e

echo "================================"
echo "PROBE MONITOR - TERMUX SETUP"
echo "================================"
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}[1/7] Atualizando pacotes...${NC}"
pkg update -y && pkg upgrade -y
echo -e "${GREEN}✓ Pacotes atualizados${NC}\n"

echo -e "${YELLOW}[2/7] Instalando Python...${NC}"
pkg install -y python
echo -e "${GREEN}✓ Python instalado${NC}\n"

echo -e "${YELLOW}[3/7] Instalando Git...${NC}"
pkg install -y git
echo -e "${GREEN}✓ Git instalado${NC}\n"

echo -e "${YELLOW}[4/7] Instalando Termux:API...${NC}"
pkg install -y termux-api
echo -e "${GREEN}✓ Termux:API instalado${NC}\n"

echo -e "${YELLOW}[5/7] Configurando armazenamento...${NC}"
termux-setup-storage
echo -e "${GREEN}✓ Armazenamento configurado${NC}\n"

echo -e "${YELLOW}[6/7] Instalando dependências Python...${NC}"
pip install requests speedtest-cli
echo -e "${GREEN}✓ Dependências instaladas${NC}\n"

echo -e "${YELLOW}[7/7] Criando diretório...${NC}"
mkdir -p ~/storage/downloads/Probe_py
echo -e "${GREEN}✓ Diretório criado${NC}\n"

echo "================================"
echo -e "${GREEN}SETUP CONCLUÍDO!${NC}"
echo "================================\n"

echo "PRÓXIMAS ETAPAS:"
echo "1. Instale Termux:API (F-Droid ou Play Store)"
echo "2. Settings > Termux:API > Permissões > Localização (Always)"
echo "3. cd ~/storage/downloads && git clone https://github.com/jvictorferreira3301/probe_monitor.git"
echo "4. Configure .env com Firebase credentials"
echo "5. python probe.py --loop 10 --speedtest --sync --sync_interval --location"
echo ""
echo -e "${GREEN}✓ Pronto para usar!${NC}"