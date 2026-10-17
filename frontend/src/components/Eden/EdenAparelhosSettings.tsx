// Éden (Parte 5): aparelhos ligados. Cada celular tem uma chave só dele; se
// um for perdido, dá para desligar só ele, pelo notebook.
import { useCallback, useEffect, useState } from 'react';
import { KeyRound, Smartphone, Trash2 } from 'lucide-react';
import { useAppStore } from '../../lib/store';
import { criarAparelho, desligarAparelho, listarAparelhos, quandoUsado, type Aparelho } from '../../lib/eden-aparelhos';

const cor2 = { color: 'var(--color-text-secondary)' };

// Celular ou tablet (tela de toque, sem "passar o mouse").
function aparelhoDeToque(): boolean {
  try {
    return window.matchMedia?.('(hover: none)').matches ?? false;
  } catch {
    return false;
  }
}
const cor3 = { color: 'var(--color-text-tertiary)' };

export function EdenAparelhosSettings() {
  const updateSettings = useAppStore((s) => s.updateSettings);
  const [lista, setLista] = useState<Aparelho[] | null>(null);
  const [eu, setEu] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const carregar = useCallback(() => {
    listarAparelhos()
      .then((r) => {
        setLista(r.aparelhos);
        setEu(r.eu);
        setErro(null);
      })
      .catch((e) => setErro((e as Error).message));
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const desligar = async (a: Aparelho) => {
    const proprio = a.id === eu;
    const pergunta = proprio
      ? `Desligar ESTE aparelho (${a.nome})? Ele vai pedir a chave ou um código novo para entrar de novo.`
      : `Desligar "${a.nome}"? Ele perde o acesso ao Éden na hora.`;
    if (!window.confirm(pergunta)) return;
    setErro(null);
    try {
      await desligarAparelho(a.id);
      if (proprio) {
        updateSettings({ apiKey: '' });
        return;
      }
      carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const chaveSoDeste = async () => {
    setErro(null);
    setAviso(null);
    try {
      const nome = aparelhoDeToque() ? 'Celular' : 'Computador';
      const novo = await criarAparelho(nome);
      updateSettings({ apiKey: novo.chave });
      setAviso('Pronto: este aparelho agora usa uma chave só dele.');
      carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <div className="flex flex-col gap-2 text-sm" style={cor2}>
      <p className="text-xs" style={cor3}>
        Cada aparelho ligado pelo código ou pelo QR code tem uma chave só dele. Se um celular for perdido, desligue só
        ele aqui (pelo notebook). A chave principal do notebook não aparece nesta lista.
      </p>
      {lista === null ? (
        <p className="text-xs" style={cor3}>
          {erro ?? 'Carregando…'}
        </p>
      ) : lista.length === 0 ? (
        <p className="text-xs" style={cor3}>
          Nenhum aparelho com chave própria ainda.
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {lista.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-2 rounded-lg px-3 py-2"
              style={{ border: '1px solid var(--color-border)' }}
            >
              <Smartphone size={14} className="shrink-0" style={cor3} />
              <div className="flex-1 min-w-0">
                <div className="truncate" style={{ color: 'var(--color-text)' }}>
                  {a.nome}
                  {a.id === eu && <span style={{ color: 'var(--color-accent)' }}> · este aparelho</span>}
                </div>
                <div className="text-[11px]" style={cor3}>
                  último uso: {quandoUsado(a.ultimo_uso)}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void desligar(a)}
                aria-label={`Desligar ${a.nome}`}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] cursor-pointer"
                style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
              >
                <Trash2 size={12} /> Desligar
              </button>
            </li>
          ))}
        </ul>
      )}
      {lista !== null && eu === null && aparelhoDeToque() && (
        <div className="flex flex-col gap-1">
          <button
            type="button"
            onClick={() => void chaveSoDeste()}
            className="self-start inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs cursor-pointer"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            <KeyRound size={12} /> Usar uma chave só deste aparelho
          </button>
          <p className="text-[11px]" style={cor3}>
            Este celular ainda usa a chave principal. Com uma chave própria, dá para desligar só ele se for perdido.
          </p>
        </div>
      )}
      {aviso && (
        <p role="status" className="text-xs" style={{ color: 'var(--color-success)' }}>
          {aviso}
        </p>
      )}
      {erro && lista !== null && (
        <p role="alert" className="text-xs" style={{ color: 'var(--color-error)' }}>
          {erro}
        </p>
      )}
    </div>
  );
}
