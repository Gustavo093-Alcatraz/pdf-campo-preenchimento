import os
import shutil
from pathlib import Path

def cleanup():
    target_dir = Path.cwd()
    patterns = ["__pycache__", ".pytest_cache", "*.pyc"]
    
    deleted_count = 0
    
    print(f"Iniciando limpeza em: {target_dir}")
    
    for item in target_dir.rglob("*"):
        try:
            # Verifica se é uma pasta de cache
            if item.is_dir() and item.name in ["__pycache__", ".pytest_cache"]:
                print(f"Removendo pasta: {item}")
                shutil.rmtree(item)
                deleted_count += 1
            # Verifica se é um arquivo .pyc
            elif item.is_file() and item.suffix == ".pyc":
                print(f"Removendo arquivo: {item}")
                item.unlink()
                deleted_count += 1
        except Exception as e:
            print(f"Erro ao remover {item}: {e}")

    print(f"\nConcluído! Total de itens removidos: {deleted_count}")

if __name__ == "__main__":
    cleanup()
