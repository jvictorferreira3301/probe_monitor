import csv
import os
import sys
import json
from datetime import datetime
import requests

# === CARREGA .env ===
def carregar_env():
    """Carrega variáveis do arquivo .env"""
    env_file = '.env'
    if os.path.exists(env_file):
        with open(env_file) as f:
            for linha in f:
                linha = linha.strip()
                if linha and not linha.startswith('#'):
                    if '=' in linha:
                        chave, valor = linha.split('=', 1)
                        os.environ[chave.strip()] = valor.strip()

carregar_env()

# === CONFIGURAÇÕES ===
CSV_FILE = '/sdcard/Download/relatorio_completo_rede.csv'
FIREBASE_DB = os.getenv('FIREBASE_DB', '')
FIREBASE_KEY = os.getenv('FIREBASE_KEY', '')

def sincronizar_firebase():
    """Lê CSV e envia dados para Firebase Realtime Database"""
    
    if not FIREBASE_DB or not FIREBASE_KEY:
        print("[-] FIREBASE_DB ou FIREBASE_KEY nao definido!")
        print("[*] Configure em .env:")
        print("    FIREBASE_DB=https://seu-projeto.firebaseio.com")
        print("    FIREBASE_KEY=sua-chave-secreta")
        return False
    
    print("\n[*] Sincronizando com Firebase...")
    
    # Verificar se CSV existe
    if not os.path.exists(CSV_FILE):
        print(f"[-] CSV nao encontrado: {CSV_FILE}")
        return False
    
    print(f"[*] Lendo CSV: {CSV_FILE}")
    
    try:
        # Ler CSV
        dados = []
        with open(CSV_FILE) as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Adicionar timestamp ISO
                try:
                    row['timestamp'] = datetime.strptime(row['Data_Hora'], '%Y-%m-%d %H:%M:%S').isoformat()
                except:
                    row['timestamp'] = datetime.now().isoformat()
                
                # Manter dados originais do CSV (sem duplicatas em lowercase)
                dados.append(row)
        
        if not dados:
            print("[-] Nenhum dado para sincronizar")
            return False
        
        print(f"[*] Total de registros: {len(dados)}")
        
        # Enviar para Firebase
        # Estrutura: /measurements/timestamp_probe_tech = dados
        inseridos = 0
        
        for row in dados:
            try:
                # Criar ID único baseado em probe_id + timestamp + tech (previne colisão entre probes)
                probe_id = row.get('PROBE_ID', 'unknown').replace(' ', '_')
                timestamp = row.get('timestamp', '').replace(':', '-').replace('T', '_')
                tech = row.get('Tecnologia', 'unknown')
                uid = f"{probe_id}_{timestamp}_{tech}"
                
                # URL do Firebase (estrutura: /measurements/probe_id/timestamp_tech = dados)
                url = f"{FIREBASE_DB}/measurements/{probe_id}/{uid}.json?auth={FIREBASE_KEY}"
                
                # Enviar dados
                resposta = requests.put(url, json=row, timeout=5)
                
                if resposta.status_code in [200, 201]:
                    inseridos += 1
                else:
                    print(f"[-] Erro ao enviar: {resposta.status_code}")
            
            except Exception as e:
                print(f"[-] Erro ao sincronizar: {e}")
        
        print(f"[+] {inseridos}/{len(dados)} registros sincronizados com sucesso!")
        print(f"[*] Estrutura Firebase: /measurements/PROBE_ID/timestamp_tech")
        return True
        
        # Stats
        try:
            url = f"{FIREBASE_DB}/measurements.json?auth={FIREBASE_KEY}&shallow=true"
            resposta = requests.get(url, timeout=5)
            if resposta.status_code == 200:
                total_docs = len(resposta.json() or {})
                print(f"[*] Total de documentos no Firebase: {total_docs}")
        except:
            pass
        
        return True
    
    except Exception as e:
        print(f"[-] Erro ao sincronizar: {e}")
        return False

def setup_firebase():
    """Setup interativo do Firebase"""
    
    print("\n" + "="*70)
    print("SETUP Firebase Realtime Database")
    print("="*70)
    
    print("\n[1] Acesse: https://console.firebase.google.com")
    print("[2] Create a new project (free)")
    print("[3] Go to Realtime Database")
    print("[4] Create Database (Start in test mode)")
    print("[5] Em Settings/Service Accounts, copie a Database URL")
    print("[6] Em Database Secrets, crie uma chave nova\n")
    
    firebase_db = input("Cole a DATABASE URL (https://seu-projeto.firebaseio.com):\n> ").strip()
    firebase_key = input("\nCole a SECRET KEY:\n> ").strip()
    
    if not firebase_db or not firebase_key:
        print("[-] URLs vazias. Cancelado.")
        return False
    
    # Testar conexão
    print("\n[*] Testando conexao...")
    try:
        url = f"{firebase_db}/.json?auth={firebase_key}"
        resposta = requests.get(url, timeout=5)
        if resposta.status_code == 200:
            print("[+] Conexao OK!")
            
            # Salvar em arquivo .env
            with open('.env', 'w') as f:
                f.write(f"FIREBASE_DB={firebase_db}\n")
                f.write(f"FIREBASE_KEY={firebase_key}\n")
            
            print("[+] URLs salvas em .env")
            return True
        else:
            print(f"[-] Erro: Status {resposta.status_code}")
            return False
    
    except Exception as e:
        print(f"[-] Erro: {e}")
        return False

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Firebase Sync - Sincroniza dados UDP com Firebase Realtime DB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python firebase_sync.py                 # Sincroniza com Firebase
  python firebase_sync.py --setup         # Setup da connection
  python firebase_sync.py --check         # Verifica dados no Firebase
        """
    )
    
    parser.add_argument('--setup', action='store_true', help='Configurar Firebase')
    parser.add_argument('--check', action='store_true', help='Verificar dados no Firebase')
    
    args = parser.parse_args()
    
    if args.setup:
        setup_firebase()
    elif args.check:
        if not FIREBASE_DB or not FIREBASE_KEY:
            print("[-] Configure Firebase primeiro: python firebase_sync.py --setup")
        else:
            try:
                url = f"{FIREBASE_DB}/measurements.json?auth={FIREBASE_KEY}&shallow=true"
                resposta = requests.get(url, timeout=5)
                if resposta.status_code == 200:
                    dados = resposta.json() or {}
                    print(f"\n[+] Total de documentos: {len(dados)}")
                    
                    if dados:
                        print("\n[+] Ultimos registros:")
                        for chave in list(dados.keys())[-5:]:
                            print(f"  {chave}")
            except Exception as e:
                print(f"[-] Erro: {e}")
    else:
        sucesso = sincronizar_firebase()
        sys.exit(0 if sucesso else 1)
