import socket
import datetime
import time
import csv
import os
import subprocess
import json
import argparse
import sys
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
SERVER_ADDRESS = ('186.228.38.168', 10050)
TOTAL_PACKETS = 100
DIR_PATH = "/sdcard/Download"
FILE_NAME = os.path.join(DIR_PATH, "relatorio_completo_rede.csv")

# === CACHE GLOBAL ===
_cached_public_ip = None
_cached_probe_id = None

def get_cell_info():
    """Captura dados da torre via Termux:API"""
    try:
        res = subprocess.run(['termux-telephony-cellinfo'], capture_output=True, text=True)
        data = json.loads(res.stdout)
        
        # Procuramos pela torre que está "registered: True"
        for tower in data:
            if tower.get('registered'):
                return tower
        return {}
    except:
        return {}

def get_location():
    """Captura latitude/longitude via Termux:API (usa network provider)"""
    try:
        res = subprocess.run(['termux-location', '-p', 'network'], capture_output=True, text=True, timeout=10)
        data = json.loads(res.stdout)
        return {
            'latitude': data.get('latitude', 'N/A'),
            'longitude': data.get('longitude', 'N/A'),
            'accuracy': data.get('accuracy', 'N/A')
        }
    except Exception as e:
        return {'latitude': 'N/A', 'longitude': 'N/A', 'accuracy': 'N/A'}

def get_probe_id():
    """Obtém PROBE_ID do .env com fallback seguro"""
    global _cached_probe_id
    if _cached_probe_id is not None:
        return _cached_probe_id
    
    probe_id = os.getenv('PROBE_ID', '').strip()
    if not probe_id:
        # Fallback: usa hostname do device
        probe_id = os.getenv('HOSTNAME', 'unknown_probe')
    
    _cached_probe_id = probe_id
    return _cached_probe_id

def get_public_ip():
    """Captura IP público com cache para evitar múltiplas requisições"""
    global _cached_public_ip
    if _cached_public_ip is not None:
        return _cached_public_ip
    
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=5)
        _cached_public_ip = response.json().get('ip', 'N/A')
    except:
        _cached_public_ip = 'N/A'
    
    return _cached_public_ip

def get_municipio_nominatim(latitude, longitude):
    """Reverse geocoding via Nominatim (OpenStreetMap) para obter municipio"""
    if latitude == 'N/A' or longitude == 'N/A':
        return 'N/A'
    
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}"
        headers = {'User-Agent': 'Probe_py/1.0'}
        response = requests.get(url, timeout=5, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            address = data.get('address', {})
            
            # Tenta encontrar municipio em diferentes chaves
            municipio = address.get('municipality') or address.get('city') or address.get('town') or 'N/A'
            return municipio
        else:
            return 'N/A'
    except Exception as e:
        return 'N/A'

def run_network_test():
    """Executa o teste de latência e perda de pacotes com análise de ordem/duplicatas"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.8)
    
    sent_timestamps = {}
    received_latencies = []
    received_packets = {}
    received_sequence = []
    received_count = 0
    out_of_order_count = 0
    out_of_order_list = []
    last_packet_id = None
    
    print(f"[*] Enviando {TOTAL_PACKETS} pacotes para {SERVER_ADDRESS[0]}...")
    
    # Envio de pacotes
    for i in range(TOTAL_PACKETS):
        data = str(i).encode()
        sent_timestamps[i] = time.perf_counter()
        sock.sendto(data, SERVER_ADDRESS)
        time.sleep(0.02)
    
    print("[*] Aguardando respostas...")
    
    # Recebimento de pacotes
    for _ in range(TOTAL_PACKETS):
        try:
            resp, _ = sock.recvfrom(1024)
            recv_time = time.perf_counter()
            pkt_id = int(resp.decode())
            
            if pkt_id in sent_timestamps:
                latency = (recv_time - sent_timestamps[pkt_id]) * 1000
                received_latencies.append(latency)
                received_sequence.append(pkt_id)
                received_count += 1
                
                # Contagem de duplicatas
                received_packets[pkt_id] = received_packets.get(pkt_id, 0) + 1
                
                # Detecção de fora de ordem
                if last_packet_id is not None and pkt_id != last_packet_id + 1:
                    out_of_order_count += 1
                    out_of_order_list.append(pkt_id)
                
                last_packet_id = pkt_id
        except socket.timeout:
            pass
    
    sock.close()
    
    # Cálculos finais
    avg_lat = sum(received_latencies) / len(received_latencies) if received_latencies else 0
    loss = ((TOTAL_PACKETS - received_count) / TOTAL_PACKETS) * 100
    duplicate_count = sum(1 for count in received_packets.values() if count > 1)
    missing_packets = sorted(set(range(TOTAL_PACKETS)) - set(received_packets.keys()))
    
    return {
        'avg_latency': avg_lat,
        'loss_percent': loss,
        'received_count': received_count,
        'out_of_order_count': out_of_order_count,
        'out_of_order_list': out_of_order_list,
        'duplicate_count': duplicate_count,
        'missing_packets': missing_packets,
        'received_sequence': received_sequence
    }

def run_speedtest():
    """Executa teste de velocidade (download/upload)"""
    try:
        import speedtest
    except ImportError:
        print("[!] speedtest-cli não instalado. Instalando...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'speedtest-cli', '-q'])
        import speedtest
    
    try:
        print("[*] Iniciando teste de velocidade (pode levar ~30-60 seg)...")
        st = speedtest.Speedtest()
        st.get_best_server()
        
        print("    [*] Testando download...")
        download_speed = st.download() / 1_000_000  # Converte para Mbps
        
        print("    [*] Testando upload...")
        upload_speed = st.upload() / 1_000_000  # Converte para Mbps
        
        results = st.results.dict()
        ping = results.get('ping', 0)
        
        print(f"[+] Speedtest finalizado!")
        print(f"    Download: {download_speed:.2f} Mbps")
        print(f"    Upload: {upload_speed:.2f} Mbps")
        print(f"    Ping: {ping:.2f} ms")
        
        return {
            'download_mbps': download_speed,
            'upload_mbps': upload_speed,
            'ping_ms': ping
        }
    except Exception as e:
        print(f"[-] Erro no speedtest: {e}")
        return {
            'download_mbps': 'N/A',
            'upload_mbps': 'N/A',
            'ping_ms': 'N/A'
        }

def save_to_csv(cell, network_test, speedtest_data=None, location_data=None):
    """Salva dados no CSV garantindo sempre 22 colunas para evitar desalinhamento"""
    os.makedirs(DIR_PATH, exist_ok=True)
    
    # Cabeçalho ÚNICO e definitivo (22 colunas com geolocation + fingerprint)
    header = [
        "Data_Hora", "Tecnologia", "PCI", "TAC", "Cell_ID",
        "RSRP_dBm", "RSRQ_dB", "SINR",
        "Latencia_UDP_ms", "Perda_%", "Out_of_Order", "Duplicados",
        "Download_Mbps", "Upload_Mbps", "Ping_Speedtest_ms",
        "Pacotes_Recebidos", "Pacotes_Faltantes", "IP_Servidor",
        "PROBE_ID", "IP_Publico",
        "Latitude", "Longitude", "Municipio"
    ]
    
    # Se não houver speedtest, forçamos os valores a serem "N/A"
    if not speedtest_data:
        speedtest_data = {'download_mbps': 'N/A', 'upload_mbps': 'N/A', 'ping_ms': 'N/A'}
    
    # Se não houver location, forçamos os valores a serem "N/A"
    if not location_data:
        location_data = {'latitude': 'N/A', 'longitude': 'N/A', 'municipio': 'N/A'}
    
    # Extrair dados da célula
    tech = cell.get('type', 'N/A')
    rsrp = cell.get('rsrp') or cell.get('ssRsrp') or 'N/A'
    rsrq = cell.get('rsrq') or cell.get('ssRsrq') or 'N/A'
    sinr = cell.get('rssnr') or cell.get('ssSinr') or 'N/A'
    pci = cell.get('pci', 'N/A')
    tac = cell.get('tac', 'N/A')
    cid = cell.get('ci') or cell.get('nci') or 'N/A'
    
    # Linha ÚNICA e definitiva (22 colunas com geolocation + fingerprint, seguindo a ordem do header)
    row = [
        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        tech.upper(), pci, tac, cid,
        rsrp, rsrq, sinr,
        f"{network_test['avg_latency']:.2f}",
        f"{network_test['loss_percent']:.2f}",
        network_test['out_of_order_count'],
        network_test['duplicate_count'],
        f"{speedtest_data['download_mbps']:.2f}" if speedtest_data['download_mbps'] != 'N/A' else 'N/A',
        f"{speedtest_data['upload_mbps']:.2f}" if speedtest_data['upload_mbps'] != 'N/A' else 'N/A',
        f"{speedtest_data['ping_ms']:.2f}" if speedtest_data['ping_ms'] != 'N/A' else 'N/A',
        network_test['received_count'],
        ";".join(map(str, network_test['missing_packets'])) if network_test['missing_packets'] else "",
        SERVER_ADDRESS[0],
        get_probe_id(),
        get_public_ip(),
        location_data['latitude'],
        location_data['longitude'],
        location_data['municipio']
    ]
    
    write_header = not os.path.isfile(FILE_NAME)
    with open(FILE_NAME, mode="a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        writer.writerow(row)

def print_results(cell, network_test, speedtest_data=None, location_data=None, test_number=None):
    """Imprime resultados no terminal"""
    tech = cell.get('type', 'N/A').upper()
    rsrp = cell.get('rsrp') or cell.get('ssRsrp') or 'N/A'
    pci = cell.get('pci', 'N/A')
    
    if test_number:
        print(f"\n{'='*70}")
        print(f"[TEST #{test_number}] {datetime.datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*70}")
    else:
        print(f"\n{'='*70}")
        print(f"[+] Teste Finalizado!")
        print(f"{'='*70}")
    
    print(f"[Signal] {rsrp} dBm ({tech}) | PCI: {pci}")
    print(f"[UDP] Latencia: {network_test['avg_latency']:.2f}ms | Perda: {network_test['loss_percent']:.2f}%")
    print(f"[Quality] {network_test['received_count']}/{TOTAL_PACKETS} pacotes | " + 
          f"Fora de ordem: {network_test['out_of_order_count']} | " +
          f"Duplicados: {network_test['duplicate_count']}")
    
    if speedtest_data:
        if speedtest_data['download_mbps'] != 'N/A':
            print(f"[Speed] DL: {speedtest_data['download_mbps']:.2f} Mbps | " +
                  f"UL: {speedtest_data['upload_mbps']:.2f} Mbps | " +
                  f"Ping: {speedtest_data['ping_ms']:.2f} ms")
        else:
            print(f"[Speed] Indisponível")
    else:
        print(f"[Speed] Nao executado (use --speedtest se desejar)")
    
    if network_test['missing_packets']:
        print(f"[Missing] {network_test['missing_packets']}")
    
    probe_id = get_probe_id()
    public_ip = get_public_ip()
    print(f"[Probe] ID: {probe_id} | IP_Publico: {public_ip}")
    
    if location_data and location_data['latitude'] != 'N/A':
        print(f"[Location] Lat: {location_data['latitude']} | Lon: {location_data['longitude']} | Municipio: {location_data['municipio']}")
    
    print(f"[File] {FILE_NAME}")

def run_single_test(speedtest_enabled=False, location_enabled=False):
    """Executa um teste único"""
    cell = get_cell_info()
    network_test = run_network_test()
    
    speedtest_data = None
    if speedtest_enabled:
        speedtest_data = run_speedtest()
    
    location_data = None
    if location_enabled:
        loc = get_location()
        municipio = get_municipio_nominatim(loc['latitude'], loc['longitude'])
        location_data = {
            'latitude': loc['latitude'],
            'longitude': loc['longitude'],
            'municipio': municipio
        }
    
    save_to_csv(cell, network_test, speedtest_data, location_data)
    print_results(cell, network_test, speedtest_data, location_data)

def run_loop_test(interval_minutes, speedtest_enabled=False, sync_sheets=False, sync_interval=10, location_enabled=False):
    """Executa testes em loop contínuo com sincronizacao opcional"""
    interval_seconds = interval_minutes * 60
    test_number = 1
    sync_counter = 0
    
    print(f"\n[*] Modo LOOPING ativado - Teste a cada {interval_minutes} minuto(s)")
    if speedtest_enabled:
        print(f"[*] Modo SPEEDTEST ativado (pode adicionar ~1 min por teste)")
    if location_enabled:
        print(f"[*] Modo LOCATION ativado (captura Lat/Lon/Municipio)")
    if sync_sheets:
        print(f"[*] Modo SYNC ativado - Sincronizara a cada {sync_interval} testes")
    print(f"[!] Pressione Ctrl+C para parar\n")
    
    try:
        while True:
            print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
            
            cell = get_cell_info()
            network_test = run_network_test()
            
            speedtest_data = None
            if speedtest_enabled:
                speedtest_data = run_speedtest()
            
            location_data = None
            if location_enabled:
                loc = get_location()
                municipio = get_municipio_nominatim(loc['latitude'], loc['longitude'])
                location_data = {
                    'latitude': loc['latitude'],
                    'longitude': loc['longitude'],
                    'municipio': municipio
                }
            
            save_to_csv(cell, network_test, speedtest_data, location_data)
            print_results(cell, network_test, speedtest_data, location_data, test_number=test_number)
            
            # Sincronizar com Firebase a cada N testes
            if sync_sheets:
                sync_counter += 1
                if sync_counter >= sync_interval:
                    print("\n[*] Sincronizando com Firebase...")
                    try:
                        from firebase_sync import sincronizar_firebase
                        sincronizar_firebase()
                    except Exception as e:
                        print(f"[-] Erro ao sincronizar: {e}")
                    sync_counter = 0
            
            test_number += 1
            
            if interval_minutes > 0:
                print(f"\n[*] Proximo teste em {interval_minutes} minuto(s)... (Ctrl+C para parar)")
                time.sleep(interval_seconds)
    
    except KeyboardInterrupt:
        print(f"\n\n[-] Looping parado pelo usuario.")
        print(f"[*] Total de testes realizados: {test_number - 1}")
        
        # Sincronizar dados finais
        if sync_sheets:
            print("[*] Sincronizando dados finais com Firebase...")
            try:
                from firebase_sync import sincronizar_firebase
                sincronizar_firebase()
            except:
                pass

# === MAIN ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Network Probe Monitor - UDP Loss + Cell Info + Speedtest + Firebase Sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python probe.py                                    # Um teste UDP (rápido)
  python probe.py --speedtest                        # Um teste UDP + Speedtest
  python probe.py --location                         # Um teste UDP + Geolocation (Lat/Lon/Municipio)
  python probe.py --loop 5                           # Testes UDP a cada 5 minutos
  python probe.py --loop 10 --speedtest              # Testes com Speedtest a cada 10 min
  python probe.py --loop 5 --location                # Testes com Geolocation a cada 5 min
  python probe.py --loop 5 --sync                    # Sync Firebase a cada 10 testes (default)
  python probe.py --loop 5 --sync --sync-interval 2  # Sync a cada 2 testes (RÁPIDO!)
  python probe.py --loop 5 --location --sync         # Testes + Geolocation + Firebase Sync
  """
    )
    
    parser.add_argument(
        '--loop', 
        type=int, 
        metavar='MINUTOS',
        help='Modo looping: executa teste a cada N minutos'
    )
    
    parser.add_argument(
        '--speedtest',
        action='store_true',
        help='Adiciona teste de velocidade (download/upload/ping)'
    )
    
    parser.add_argument(
        '--simulate',
        action='store_true',
        help='[DEPRECADO] Modo simulação para testes em PC'
    )    
    parser.add_argument(
        '--sync',
        action='store_true',
        help='Sincroniza dados com Firebase Realtime Database (a cada N testes)'
    )
    
    parser.add_argument(
        '--sync-interval',
        type=int,
        default=10,
        metavar='N',
        help='Sincroniza a cada N testes (default: 10, use 2 pra testar rápido)'
    )
    
    parser.add_argument(
        '--location',
        action='store_true',
        help='Captura geolocation (latitude/longitude/municipio) via Nominatim API'
    )
    
    args = parser.parse_args()
    
    try:
        if args.loop is not None:
            if args.loop < 1:
                print("[-] Erro: --loop deve ser >= 1")
                sys.exit(1)
            run_loop_test(args.loop, args.speedtest, args.sync, args.sync_interval, args.location)
        else:
            run_single_test(args.speedtest, args.location)
    
    except Exception as e:
        print(f"[-] Erro: {e}")
        sys.exit(1)
