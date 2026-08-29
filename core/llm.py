import requests
from config import OLLAMA_URL, OLLAMA_MODEL, OLLAMA_KEEP_ALIVE


class LLM:

    def __init__(self):
        # Antes lidos direto de os.getenv aqui, duplicando o que já existe
        # em config.py — agora há uma única fonte de verdade.
        self.url = OLLAMA_URL
        self.model = OLLAMA_MODEL

    def healthcheck(self) -> bool:
        """Verifica se o servidor do Ollama está rodando e acessível."""
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=3)
            return response.status_code == 200
        except Exception:
            return False

    def ask(self, prompt: str) -> str:
        """Envia o prompt para o Ollama e retorna a resposta em texto."""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "system": (
                    "Você é o Jarvis, um assistente de voz brasileiro. Converse"
                    " de forma natural e calorosa, como um amigo prestativo —"
                    " nada de respostas robóticas ou genéricas. Se o usuário"
                    " mandar só um cumprimento informal (\"e aí\", \"oi\", \"bom"
                    " dia\"), responda o cumprimento de volta antes de"
                    " perguntar no que pode ajudar, sem inventar assuntos que"
                    " não foram ditos. Para pedidos concretos, seja direto e"
                    " objetivo em no máximo 2 ou 3 frases, sempre em português."
                    " IMPORTANTE: você NÃO executa nada no computador do"
                    " usuário — abrir/fechar programas é tratado por um"
                    " sistema separado antes de chegar até você. Se pedirem"
                    " para abrir, fechar ou controlar algo no PC e você"
                    " estiver recebendo a pergunta, é porque esse app não"
                    " está configurado; diga isso claramente e nunca finja"
                    " ter executado uma ação."
                ),
            }

            response = requests.post(
                f"{self.url}/api/generate", json=payload, timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("response", "").strip()
            else:
                return f"Erro no servidor Ollama (Código {response.status_code})."

        except requests.exceptions.ConnectionError:
            return (
                "Não foi possível conectar ao Ollama. Verifique se o serviço"
                " está rodando."
            )
        except Exception as e:
            return f"Erro ao processar resposta: {e}"

    def chat(self, prompt: str) -> str:
        """Redireciona para o método ask para manter compatibilidade com o main.py."""
        return self.ask(prompt)