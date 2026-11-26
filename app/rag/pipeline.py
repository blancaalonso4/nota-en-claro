"""Pipeline de principio a fin: recuperar -> (reordenar) -> generar -> validar cita."""
from __future__ import annotations

from .citas import validar
from .config import ConfigRAG, fijar_semillas
from .corpus import cargar_manifiesto
from .generador import GeneradorOllama
from .indice import Indice
from .prompt import mensajes_para
from .recuperacion import Reordenador, buscar


class SistemaRAG:
    def __init__(self, cfg: ConfigRAG | None = None):
        self.cfg = cfg or ConfigRAG()
        fijar_semillas(self.cfg.semilla)
        self.manifiesto = cargar_manifiesto(self.cfg.manifiesto)
        self.indice = Indice.cargar_o_construir(self.cfg)
        self.generador = GeneradorOllama(self.cfg)
        self.reordenador = Reordenador(self.cfg.reordenador) if self.cfg.usar_reordenador else None

    def recuperar(self, pregunta: str) -> list[dict]:
        orden, _ = buscar(self.indice, pregunta)
        if self.reordenador:
            n = self.cfg.n_candidatos
            orden = self.reordenador.reordenar(pregunta, orden[:n], self.indice.chunks) + orden[n:]
        return [self.indice.chunks[i] for i in orden[:self.cfg.k]]

    def responder(self, pregunta: str) -> dict:
        recuperados = self.recuperar(pregunta)
        msgs = mensajes_para(pregunta, recuperados, self.manifiesto)
        g = self.generador.generar(msgs)
        v = validar(pregunta, g['texto'], recuperados)
        fuente = {}
        if not v['abstiene']:
            c = next(c for c in recuperados if c['chunk_id'] == v['chunk_citado'])
            meta = self.manifiesto.get(c['doc_id'], {})
            fuente = {'doc_id': c['doc_id'], 'titulo': meta.get('titulo', ''),
                      'fecha': meta.get('fecha_documento', ''), 'pagina': c['pagina'], 'chunk_id': c['chunk_id']}
        return {**v, 'fuente': fuente, 'fragmentos': [c['chunk_id'] for c in recuperados],
                'salida_modelo': g['texto'], 'tokens_entrada': g['tokens_entrada'],
                'tokens_salida': g['tokens_salida'], 'segundos_generar': g['segundos']}


def formatear(r: dict) -> str:
    if r['abstiene']:
        return 'No consta en los documentos del corpus de Nota en Claro, así que no puedo contestarlo.'
    f = r['fuente']
    return (f"{r['respuesta']}\n\nFuente: «{r['cita']}» — {f['titulo']} "
            f"[{f['doc_id']}, {f['fecha'] or 's. f.'}, pág. {f['pagina']}, {f['chunk_id']}]")
