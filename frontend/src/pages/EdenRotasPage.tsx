// Éden (Parte 4): rotas e trânsito. Trajetos salvos (ex.: Casa → Trabalho)
// com o tempo agora, com trânsito (TomTom), e a comparação de caminhos (até 3,
// com as vias principais). Precisa da chave do TomTom no .env do servidor;
// sem ela, a página só explica como ligar.
import { useCallback, useEffect, useState } from 'react';
import { Car, LocateFixed, MapPin, RefreshCw, Route, Search, Trash2 } from 'lucide-react';
import { EdenPage, EdenSection, Empty, ErrorLine, GhostButton, PrimaryButton, inputStyle } from '../components/Eden/EdenUi';
import {
  apagarTrajeto,
  buscarEndereco,
  caminhosDoTrajeto,
  caminhosEntre,
  criarTrajeto,
  definirUsarLocal,
  diferenca,
  lerCoordenadas,
  localDoAparelho,
  resumoCaminho,
  resumoTempo,
  statusRotas,
  temposTrajetos,
  usarLocalNaConversa,
  type Caminho,
  type Ponto,
  type ResultadoEndereco,
  type TempoTrajeto,
  type Trajeto,
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

function ListaCaminhos({ rotas }: { rotas: Caminho[] }) {
  if (rotas.length === 0) return null;
  const maisRapido = rotas[0];
  return (
    <ol className="flex flex-col gap-1 mt-1">
      {rotas.map((c, i) => (
        <li key={i} className="text-xs flex gap-1.5" style={i === 0 ? { color: 'var(--color-text)' } : cor2}>
          <span className="shrink-0 font-medium">{i + 1}.</span>
          <span>
            {resumoCaminho(c)}
            {i === 0 ? (
              <strong style={{ color: 'var(--color-success)' }}> · mais rápido</strong>
            ) : (
              <span style={cor3}> · {diferenca(c, maisRapido) || 'quase igual'}</span>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}

function CaminhosDoTrajeto({ id }: { id: number }) {
  const [rotas, setRotas] = useState<Caminho[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    let ativo = true;
    caminhosDoTrajeto(id)
      .then((r) => {
        if (ativo) setRotas(r.rotas);
      })
      .catch((e) => {
        if (ativo) setErro((e as Error).message);
      });
    return () => {
      ativo = false;
    };
  }, [id]);
  if (erro) return <ErrorLine message={erro} />;
  if (!rotas) return <p className="text-xs mt-1" style={cor3}>Comparando caminhos…</p>;
  return <ListaCaminhos rotas={rotas} />;
}

const MINHA_LOCALIZACAO = 'local';

function ParaOndeAgora({ trajetos }: { trajetos: Trajeto[] }) {
  // Pontos salvos (sem repetir) para servir de partida.
  const pontos: Ponto[] = [];
  for (const t of trajetos) {
    for (const p of [t.origem, t.destino]) {
      if (!pontos.some((q) => q.latitude === p.latitude && q.longitude === p.longitude)) pontos.push(p);
    }
  }
  const [partida, setPartida] = useState<string>(MINHA_LOCALIZACAO);
  const [destino, setDestino] = useState<Ponto | null>(null);
  const [rotas, setRotas] = useState<Caminho[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const ver = async () => {
    if (!destino) return;
    setErro(null);
    setRotas(null);
    setOcupado(true);
    try {
      let origem: string | null;
      if (partida === MINHA_LOCALIZACAO) {
        origem = await localDoAparelho();
        if (!origem) {
          setErro('Não consegui a localização. Permita a localização para o Éden no navegador ou escolha um ponto salvo.');
          return;
        }
      } else {
        const p = pontos[Number(partida)];
        origem = `${p.latitude},${p.longitude}`;
      }
      setRotas((await caminhosEntre(origem, `${destino.latitude},${destino.longitude}`)).rotas);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="w-16 shrink-0 text-xs" style={cor3}>Saindo de</span>
        <select
          value={partida}
          onChange={(e) => setPartida(e.target.value)}
          aria-label="Saindo de"
          className="flex-1 min-w-0 px-3 py-2 rounded-lg text-sm outline-none"
          style={inputStyle}
        >
          <option value={MINHA_LOCALIZACAO}>Minha localização agora</option>
          {pontos.map((p, i) => (
            <option key={`${p.latitude},${p.longitude}`} value={String(i)}>
              {p.nome}
            </option>
          ))}
        </select>
      </div>
      <EscolherPonto rotulo="Para" valor={destino} onEscolher={setDestino} />
      <div>
        <PrimaryButton onClick={() => void ver()} disabled={!destino || ocupado}>
          <Route size={12} /> {ocupado ? 'Comparando…' : 'Comparar caminhos'}
        </PrimaryButton>
      </div>
      <ErrorLine message={erro} />
      {rotas && <ListaCaminhos rotas={rotas} />}
    </div>
  );
}

function LocalNaConversa() {
  const [ligado, setLigado] = useState(usarLocalNaConversa);
  const [aviso, setAviso] = useState<string | null>(null);
  const trocar = async (valor: boolean) => {
    setAviso(null);
    if (valor) {
      // Pede a permissão agora (no iPhone aparece o aviso do navegador).
      const local = await localDoAparelho();
      if (!local) {
        setAviso('O navegador não deu a localização. Permita a localização para o Éden e tente de novo.');
        return;
      }
    }
    definirUsarLocal(valor);
    setLigado(valor);
  };
  return (
    <div className="flex flex-col gap-1 text-sm" style={cor2}>
      <label className="flex items-start gap-2 cursor-pointer">
        <input type="checkbox" checked={ligado} onChange={(e) => void trocar(e.target.checked)} className="mt-1" />
        <span>
          Quando eu perguntar um caminho na conversa, sair da <strong>localização deste aparelho</strong>.
        </span>
      </label>
      <p className="text-[11px]" style={cor3}>
        <LocateFixed size={11} className="inline -mt-0.5 mr-1" />
        Só vai quando a mensagem é sobre caminho ou trânsito, arredondada (~10 m), e o Éden não guarda. Desligado, ele sai da
        origem do primeiro trajeto salvo.
      </p>
      <ErrorLine message={aviso} />
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
  const [comparando, setComparando] = useState<number | null>(null);

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
                      {comparando === t.trajeto.id && <CaminhosDoTrajeto id={t.trajeto.id} />}
                    </div>
                    <button
                      type="button"
                      onClick={() => setComparando((atual) => (atual === t.trajeto.id ? null : t.trajeto.id))}
                      aria-expanded={comparando === t.trajeto.id}
                      aria-label={`Comparar caminhos de ${t.trajeto.nome}`}
                      title="Comparar caminhos"
                      className="p-1 rounded cursor-pointer"
                      style={comparando === t.trajeto.id ? { color: 'var(--color-accent)' } : cor3}
                    >
                      <Route size={13} />
                    </button>
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
          <EdenSection title="Para onde agora?">
            <ParaOndeAgora trajetos={tempos.map((t) => t.trajeto)} />
          </EdenSection>
          <EdenSection title="Novo trajeto">
            <NovoTrajeto onCriado={() => void carregar()} />
          </EdenSection>
          <EdenSection title="Na conversa">
            <LocalNaConversa />
            <p className="text-[11px] mt-2" style={cor3}>
              Pergunte, por exemplo: "melhor caminho agora para o Posto 4?". O Éden compara até 3 caminhos com o trânsito de
              agora.
            </p>
          </EdenSection>
        </>
      )}
    </EdenPage>
  );
}
