"""Carga simulada do Aggron: 3 cenarios cobrindo o caminho critico.

Como rodar (DEV/STAGING SOMENTE — nunca prod):
    locust -f tests/load/locustfile.py --host=http://localhost:5050 \
           --users=50 --spawn-rate=5 --run-time=2m

Headless:
    locust -f tests/load/locustfile.py --host=http://localhost:5050 \
           --users=50 --spawn-rate=5 --run-time=2m --headless

Pesos (entre cenarios):
- LanchoneteUser: 50% — caminho "lanchonete fecha pedido" (mais comum)
- FornecedorUser: 30% — caminho "fornecedor coloca preco de partida"
- AdminUser:      20% — caminho "admin modera + transita rodada"

Setup esperado no banco-alvo:
- 1 admin: admin@aggron.com.br / admin123
- N lanchonetes: smash@demo.com (etc) / demo123
- M fornecedores: vendas@dsulcarnes.demo (etc) / demo123
- Pelo menos 1 rodada aberta com catalogo

Esses sao os mesmos seeds de dev. NAO rodar contra prod — abrira pedidos
e cotacoes reais no DB.
"""
import re

from locust import HttpUser, task, between


CSRF_RE = re.compile(rb'name="csrf_token"[^>]*value="([^"]+)"')


def _extract_csrf(response):
    m = CSRF_RE.search(response.content)
    return m.group(1).decode() if m else None


class _AuthBase(HttpUser):
    """Classe base: faz login no on_start e mantem sessao via cookies."""
    abstract = True
    wait_time = between(1, 3)
    email = ""
    senha = ""

    def on_start(self):
        r = self.client.get("/login")
        token = _extract_csrf(r)
        self.client.post("/login", data={
            "email": self.email,
            "senha": self.senha,
            "csrf_token": token,
        })


class LanchoneteUser(_AuthBase):
    """50% do trafego: lanchonete navegando + fechando pedido."""
    weight = 50
    email = "smash@demo.com"
    senha = "demo123"

    @task(3)
    def dashboard(self):
        self.client.get("/dashboard")

    @task(2)
    def catalogo(self):
        # Catalogo eh a tela mais pesada (joins de produto + preco_partida).
        self.client.get("/pedidos/catalogo", name="/pedidos/catalogo")

    @task(2)
    def listar_pedidos(self):
        self.client.get("/pedidos", name="/pedidos")

    @task(1)
    def historico(self):
        self.client.get("/historico", name="/historico")

    @task(1)
    def ver_minhas_rodadas(self):
        self.client.get("/historico/analytics", name="/historico/analytics")


class FornecedorUser(_AuthBase):
    """30% do trafego: fornecedor entrando, vendo demanda, indo cotar."""
    weight = 30
    email = "vendas@dsulcarnes.demo"
    senha = "demo123"

    @task(3)
    def dashboard(self):
        self.client.get("/fornecedor/dashboard")

    @task(2)
    def analytics(self):
        self.client.get("/fornecedor/analytics")

    @task(1)
    def pnl(self):
        # P&L tem agregacao pesada — bom canario de regressao.
        self.client.get("/fornecedor/pnl", name="/fornecedor/pnl")


class AdminUser(_AuthBase):
    """20% do trafego: admin operando rodada (tela de moderacao + analytics)."""
    weight = 20
    email = "admin@aggron.com.br"
    senha = "admin123"

    @task(3)
    def dashboard(self):
        self.client.get("/dashboard")

    @task(2)
    def listar_rodadas(self):
        self.client.get("/rodadas", name="/rodadas")

    @task(2)
    def listar_fornecedores(self):
        self.client.get("/admin/fornecedores", name="/admin/fornecedores")

    @task(2)
    def listar_lanchonetes(self):
        self.client.get("/admin/lanchonetes", name="/admin/lanchonetes")

    @task(1)
    def analytics(self):
        self.client.get("/admin/analytics", name="/admin/analytics")

    @task(1)
    def relatorio(self):
        self.client.get("/admin/relatorio", name="/admin/relatorio")
