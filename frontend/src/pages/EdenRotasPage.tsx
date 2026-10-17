// Éden (Parte 4): rotas e trânsito. Trajetos salvos (ex.: Casa → Trabalho)
// com o tempo agora, com trânsito (TomTom). Precisa da chave do TomTom no
// .env do servidor; sem ela, a página só explica como ligar.
import { useCallback, useEffect, useState } from 'react';
import { Car, MapPin, RefreshCw, Search, Trash2 } from 'lucide-react';
import { EdenPage, EdenSection, Empty, ErrorLine, GhostButton, PrimaryButton, inputStyle } from '../components/Eden/EdenUi';
import {
  apagarTrajeto,
  buscarEndereco,
  criarTrajeto,
  lerCoordenadas,
  resumoTempo,
  statusRotas,
  temposTrajetos,
  type Ponto,
  type ResultadoEndereco,
  type TempoTrajeto,
} from '../lib/eden-rotas';

const cor2 = { color: 'var(--color-text-secondary)' };
const cor3 = { color: 'var(--color-text-tertiary)' };

function EscolherPonto({ rotulo, valor, onEscolher }: { rotulo: string; valor: Ponto | null; onEscolher: (p: Ponto | null) => void }) {
  const [texto, setTexto] = useState('');
  const [resultados, setResultados] = useState<ResultadoEndereco[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const buscar = async () => {
    setErro(null);
    const coords = lerCoordenadas(texto);
    if (coords) {
      onEscolher({ nome: `${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`, ...coords });
      setResultados(null);
      return;
    }
    setOcupado(true);
    try {
      setResultados((await buscarEndereco(texto)).resultados);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  if (valor) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="w-16 shrink-0 text-xs" style={cor3}>{rotulo}</span>
        <span className="flex-1 min-w-0 truncate" style={{ color: 'var(--color-text)' }}>
          <MapPin size={12} className="inline mr-1 -mt-0.5" />
          {valor.nome}
        </span>
        <GhostButton onClick={() => onEscolher(null)}>Trocar</GhostButton>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <span className="w-16 shrink-0 text-xs" style={cor3}>{rotulo}</span>
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && texto.trim().length >= 3) void buscar();
          }}
          placeholder="Endereço, lugar ou coordenadas"
          aria-label={`${rotulo}: endereço`}
          className="flex-1 min-w-0 px-3 py-2 rounded-lg text-sm outline-none"
          style={inputStyle}
        />
        <GhostButton onClick={() => void buscar()} disabled={ocupado || texto.trim().length < 3}>
          <Search size={12} /> Buscar
        </GhostButton>
      </div>
      {resultados && resultados.length === 0 && (
        <p className="text-xs ml-[4.5rem]" style={cor3}>Nada encontrado. Tente o endereço com número e cidade.</p>
      )}
      {resultados && resultados.length > 0 && (
        <ul className="flex flex-col gap-1 ml-[4.5rem]">
          {resultados.map((r) => (
            <li key={`${r.latitude},${r.longitude}`}>
              <button
                type="button"
                onClick={() => {
                  onEscolher({ nome: r.nome, latitude: r.latitude, longitude: r.longitude });
                  setResultados(null);
                }}
                className="text-left text-xs cursor-pointer hover:underline"
                style={{ color: 'var(--color-text)' }}
              >
                {r.nome}
                {r.endereco && r.endereco !== r.nome && <span style={cor3}> · {r.endereco}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      <ErrorLine message={erro} />
    </div>
  );
}

function NovoTrajeto({ onCriado }: { onCriado: () => void }) {
  const [nome, setNome] = useState('');
  const [origem, setOrigem] = useState<Ponto | null>(null);
  const [destino, setDestino] = useState<Ponto | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const salvar = async () => {
    if (!origem || !destino) return;
    setErro(null);
    try {
      await criarTrajeto({ nome: nome.trim() || undefined, origem, destino });
      setNome('');
      setOrigem(null);
      setDestino(null);
      onCriado();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <EscolherPonto rotulo="Origem" valor={origem} onEscolher={setOrigem} />
      <EscolherPonto rotulo="Destino" valor={destino} onEscolher={setDestino} />
      <div className="flex items-center gap-2">
        <span className="w-16 shrink-0 text-xs" style={cor3}>Nome</span>
        <input
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Ex.: Casa → Trabalho (opcional)"
          aria-label="Nome do trajeto"
          className="flex-1 min-w-0 px-3 py-2 rounded-lg text-sm outline-none"
          style={inputStyle}
        />
        <PrimaryButton onClick={() => void salvar()} disabled={!origem || !destino}>
          Salvar trajeto
        </PrimaryButton>
      </div>
      <ErrorLine message={erro} />
    </div>
  );
}

export function EdenRotasPage() {
  const [configurado, setConfigurado] = useState<boolean | null>(null);
  const [tempos, setTempos] = useState<TempoTrajeto[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async (atualizar = false) => {
    setCarregando(true);
    try {
      const s = await statusRotas();
      setConfigurado(s.configurado);
      if (s.configurado) {
        setTempos((await temposTrajetos(atualizar)).tempos);
      } else {
        setTempos([]);
      }
      setErro(null);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  return (
    <EdenPage
      title="Rotas e trânsito"
      actions={
        configurado ? (
          <GhostButton onClick={() => void carregar(true)} disabled={carregando}>
            <RefreshCw size={12} /> Atualizar
          </GhostButton>
        ) : undefined
      }
    >
      <ErrorLine message={erro} />
      {configurado === null ? (
        <Empty>Carregando…</Empty>
      ) : !configurado ? (
        <EdenSection title="Ainda não configurado">
          <div className="flex flex-col gap-2 text-sm" style={cor2}>
            <p>
              O Éden calcula o tempo de carro com o trânsito de agora pelo <strong>TomTom</strong>. A conta é grátis e
              não pede cartão.
            </p>
            <ol className="list-decimal ml-5 flex flex-col gap-1">
              <li>Crie a conta em developer.tomtom.com e copie a chave (Dashboard → Keys).</li>
              <li>
                No arquivo <code>.env</code> do Éden, acrescente <code>TOMTOM_API_KEY=</code> com a chave logo depois do
                <code>=</code> (sem <code>#</code>, sem espaços).
              </li>
              <li>Rode o iniciar-eden de novo.</li>
            </ol>
            <p className="text-xs" style={cor3}>
              O TomTom recebe só as coordenadas de origem e destino dos trajetos (e o texto da busca de endereço).
            </p>
          </div>
        </EdenSection>
      ) : (
        <>
          <EdenSection title="Trajetos">
            {tempos.length === 0 ? (
              <Empty>Nenhum trajeto ainda. Salve o primeiro abaixo (ex.: Casa → Trabalho).</Empty>
            ) : (
              <ul className="flex flex-col gap-2">
                {tempos.map((t) => (
                  <li
                    key={t.trajeto.id}
                    className="flex items-start gap-3 rounded-lg px-3 py-2"
                    style={{ border: '1px solid var(--color-border)' }}
                  >
                    <Car size={16} className="mt-0.5 shrink-0" style={{ color: 'var(--color-accent)' }} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
                        {t.trajeto.nome}
                      </div>
                      <div className="text-xs" style={t.erro ? { color: 'var(--color-warning)' } : cor2}>
                        {resumoTempo(t)}
                      </div>
                      <div className="text-[11px] truncate" style={cor3}>
                        {t.trajeto.origem.nome} → {t.trajeto.destino.nome}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm(`Apagar o trajeto "${t.trajeto.nome}"?`)) {
                          void apagarTrajeto(t.trajeto.id).then(() => carregar());
                        }
                      }}
                      aria-label={`Apagar ${t.trajeto.nome}`}
                      className="p-1 rounded cursor-pointer"
                      style={cor3}
                    >
                      <Trash2 size={13} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-[11px] mt-2" style={cor3}>
              De carro, com o trânsito de agora. Dados: TomTom. O Éden guarda o resultado por 5 minutos.
            </p>
          </EdenSection>
          <EdenSection title="Novo trajeto">
            <NovoTrajeto onCriado={() => void carregar()} />
          </EdenSection>
        </>
      )}
    </EdenPage>
  );
}
