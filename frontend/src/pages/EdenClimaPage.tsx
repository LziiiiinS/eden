// Éden (Parte 4): clima, vento e ondas. Começa desligado; ao ligar, o
// servidor consulta o Open-Meteo (grátis, sem conta) só com as coordenadas
// dos lugares cadastrados. Tabela das próximas horas no estilo Windguru.
import { useCallback, useEffect, useState } from 'react';
import { ArrowUp, CloudSun, MapPin, RefreshCw, Search, Star, Trash2 } from 'lucide-react';
import { EdenPage, EdenSection, Empty, ErrorLine, GhostButton, PrimaryButton, inputStyle } from '../components/Eden/EdenUi';
import {
  apagarLugar,
  buscarLugar,
  corVento,
  criarLugar,
  descricaoTempo,
  lerCoordenadas,
  ligarClima,
  nos,
  numero,
  previsaoDoLugar,
  rotuloDia,
  rumo,
  statusClima,
  tornarPrincipal,
  type Lugar,
  type Previsao,
  type ResultadoBusca,
} from '../lib/eden-clima';

const cor2 = { color: 'var(--color-text-secondary)' };
const cor3 = { color: 'var(--color-text-tertiary)' };

function Seta({ graus }: { graus: number | null | undefined }) {
  if (graus === null || graus === undefined) return <span>–</span>;
  // A direção diz de onde vem; a seta aponta para onde vai.
  return (
    <span className="inline-flex flex-col items-center" title={`de ${rumo(graus)} (${Math.round(graus)}°)`}>
      <ArrowUp size={14} style={{ transform: `rotate(${graus + 180}deg)` }} aria-hidden />
      <span className="text-[10px]">{rumo(graus)}</span>
    </span>
  );
}

function Tabela({ previsao }: { previsao: Previsao }) {
  const horas = previsao.horas.filter((_, i) => i % 3 === 0);
  const mar = previsao.mar;
  const linha = 'px-1.5 py-1 text-center whitespace-nowrap';
  const titulo = 'px-2 py-1 text-left whitespace-nowrap sticky left-0 z-10';
  const fundoTitulo = { background: 'var(--color-bg)', color: 'var(--color-text-secondary)' };
  return (
    <div className="overflow-x-auto rounded-lg" style={{ border: '1px solid var(--color-border)' }}>
      <table className="text-xs border-collapse" aria-label="Previsão de 3 em 3 horas">
        <tbody>
          <tr>
            <th className={titulo} style={fundoTitulo}>Dia</th>
            {horas.map((h) => (
              <td key={h.hora} className={linha} style={cor3}>
                {h.hora.endsWith('T00:00') || h === horas[0] ? rotuloDia(h.hora.slice(0, 10)) : ''}
              </td>
            ))}
          </tr>
          <tr>
            <th className={titulo} style={fundoTitulo}>Hora</th>
            {horas.map((h) => (
              <td key={h.hora} className={linha} style={cor2}>{h.hora.slice(11, 13)}h</td>
            ))}
          </tr>
          <tr>
            <th className={titulo} style={fundoTitulo}>Vento (nós)</th>
            {horas.map((h) => (
              <td key={h.hora} className={`${linha} font-medium`} style={{ background: corVento(nos(h.vento_kmh)) }}>
                {nos(h.vento_kmh) ?? '–'}
              </td>
            ))}
          </tr>
          <tr>
            <th className={titulo} style={fundoTitulo}>Rajada (nós)</th>
            {horas.map((h) => (
              <td key={h.hora} className={linha} style={{ background: corVento(nos(h.rajada_kmh)) }}>
                {nos(h.rajada_kmh) ?? '–'}
              </td>
            ))}
          </tr>
          <tr>
            <th className={titulo} style={fundoTitulo}>Direção</th>
            {horas.map((h) => (
              <td key={h.hora} className={linha}><Seta graus={h.vento_dir} /></td>
            ))}
          </tr>
          {mar && (
            <>
              <tr>
                <th className={titulo} style={fundoTitulo}>Ondas (m)</th>
                {horas.map((h) => (
                  <td key={h.hora} className={`${linha} font-medium`}>{numero(h.ondas_m, 1)}</td>
                ))}
              </tr>
              <tr>
                <th className={titulo} style={fundoTitulo}>Período (s)</th>
                {horas.map((h) => (
                  <td key={h.hora} className={linha}>{numero(h.ondas_s)}</td>
                ))}
              </tr>
              <tr>
                <th className={titulo} style={fundoTitulo}>Dir. ondas</th>
                {horas.map((h) => (
                  <td key={h.hora} className={linha}><Seta graus={h.ondas_dir} /></td>
                ))}
              </tr>
              <tr>
                <th className={titulo} style={fundoTitulo}>Swell (m / s)</th>
                {horas.map((h) => (
                  <td key={h.hora} className={linha} style={cor2}>
                    {numero(h.swell_m, 1)} / {numero(h.swell_s)}
                  </td>
                ))}
              </tr>
            </>
          )}
          <tr>
            <th className={titulo} style={fundoTitulo}>Temp. (°C)</th>
            {horas.map((h) => (
              <td key={h.hora} className={linha}>{numero(h.temperatura)}</td>
            ))}
          </tr>
          <tr>
            <th className={titulo} style={fundoTitulo}>Chuva (mm)</th>
            {horas.map((h) => (
              <td key={h.hora} className={linha} style={cor2} title={`${numero(h.chuva_prob)}% de chance`}>
                {h.chuva_mm ? numero(h.chuva_mm, 1) : ''}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function AdicionarLugar({ onAdicionado }: { onAdicionado: () => void }) {
  const [busca, setBusca] = useState('');
  const [resultados, setResultados] = useState<ResultadoBusca[] | null>(null);
  const [nomeManual, setNomeManual] = useState('');
  const [coordenadas, setCoordenadas] = useState('');
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const buscar = async () => {
    setErro(null);
    setOcupado(true);
    try {
      setResultados((await buscarLugar(busca)).resultados);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  const adicionar = async (dados: { nome: string; tipo: 'cidade' | 'praia'; latitude: number; longitude: number }) => {
    setErro(null);
    try {
      await criarLugar(dados);
      setResultados(null);
      setBusca('');
      setNomeManual('');
      setCoordenadas('');
      onAdicionado();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const manual = lerCoordenadas(coordenadas);

  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="flex flex-col gap-1.5">
        <span className="text-xs" style={cor3}>Buscar cidade ou praia pelo nome</span>
        <div className="flex gap-2">
          <input
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && busca.trim().length >= 2) void buscar();
            }}
            placeholder="Ex.: Florianópolis"
            aria-label="Nome do lugar"
            className="flex-1 min-w-0 px-3 py-2 rounded-lg text-sm outline-none"
            style={inputStyle}
          />
          <GhostButton onClick={() => void buscar()} disabled={ocupado || busca.trim().length < 2}>
            <Search size={12} /> Buscar
          </GhostButton>
        </div>
        {resultados && resultados.length === 0 && <p className="text-xs" style={cor3}>Nada encontrado.</p>}
        {resultados && resultados.length > 0 && (
          <ul className="flex flex-col gap-1">
            {resultados.map((r) => (
              <li key={`${r.latitude},${r.longitude}`} className="flex items-center gap-2 text-xs flex-wrap">
                <span className="flex-1 min-w-0" style={{ color: 'var(--color-text)' }}>
                  {r.nome}
                  <span style={cor3}> · {r.regiao}</span>
                </span>
                <GhostButton onClick={() => void adicionar({ ...r, tipo: 'cidade' })}>+ cidade</GhostButton>
                <GhostButton onClick={() => void adicionar({ ...r, tipo: 'praia' })}>+ praia</GhostButton>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        <span className="text-xs" style={cor3}>
          Ou um pico pelas coordenadas: no Google Maps, toque e segure no mar perto do pico e copie os
          números (ex.: -27.6025, -48.4320).
        </span>
        <div className="flex gap-2 flex-wrap">
          <input
            value={nomeManual}
            onChange={(e) => setNomeManual(e.target.value)}
            placeholder="Nome (ex.: Praia Mole)"
            aria-label="Nome do pico"
            className="flex-1 min-w-[9rem] px-3 py-2 rounded-lg text-sm outline-none"
            style={inputStyle}
          />
          <input
            value={coordenadas}
            onChange={(e) => setCoordenadas(e.target.value)}
            placeholder="-27.6025, -48.4320"
            aria-label="Coordenadas"
            className="flex-1 min-w-[9rem] px-3 py-2 rounded-lg text-sm outline-none"
            style={inputStyle}
          />
          <GhostButton
            onClick={() => manual && void adicionar({ nome: nomeManual.trim(), tipo: 'praia', ...manual })}
            disabled={!manual || !nomeManual.trim()}
          >
            <MapPin size={12} /> Adicionar praia
          </GhostButton>
        </div>
      </div>
      <ErrorLine message={erro} />
    </div>
  );
}

export function EdenClimaPage() {
  const [ligado, setLigado] = useState<boolean | null>(null);
  const [lugares, setLugares] = useState<Lugar[]>([]);
  const [fonte, setFonte] = useState('Open-Meteo');
  const [escolhido, setEscolhido] = useState<number | null>(null);
  const [previsao, setPrevisao] = useState<Previsao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const s = await statusClima();
      setLigado(s.ligado);
      setLugares(s.lugares);
      setFonte(s.fonte);
      setEscolhido((atual) =>
        atual !== null && s.lugares.some((l) => l.id === atual)
          ? atual
          : (s.lugares.find((l) => l.principal) ?? s.lugares[0])?.id ?? null,
      );
      setErro(null);
    } catch (e) {
      setErro((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const verPrevisao = useCallback(async (id: number, atualizar = false) => {
    setCarregando(true);
    try {
      setPrevisao(await previsaoDoLugar(id, atualizar));
      setErro(null);
    } catch (e) {
      setPrevisao(null);
      setErro((e as Error).message);
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    if (ligado && escolhido !== null) void verPrevisao(escolhido);
    else setPrevisao(null);
  }, [ligado, escolhido, verPrevisao]);

  const ligar = async (valor: boolean) => {
    if (!valor && !window.confirm('Desligar clima e ondas? Os lugares ficam guardados.')) return;
    try {
      await ligarClima(valor);
      await carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const atual = lugares.find((l) => l.id === escolhido) ?? null;

  return (
    <EdenPage title="Clima, vento e ondas">
      <ErrorLine message={erro} />
      {ligado === null ? (
        <Empty>Carregando…</Empty>
      ) : !ligado ? (
        <EdenSection title="Desligado">
          <div className="flex flex-col items-start gap-3 text-sm" style={cor2}>
            <p>
              Ao ligar, o Éden consulta o <strong>Open-Meteo</strong>: grátis para uso pessoal, sem conta e sem
              chave. Só vão as <strong>coordenadas</strong> dos lugares que você cadastrar (cidade e praias).
              Nada da conversa sai daqui.
            </p>
            <p>
              Você vê vento, rajadas, ondas e chuva das próximas 72 horas, e o Éden responde perguntas como
              "vai ter onda amanhã na Praia Mole?".
            </p>
            <PrimaryButton onClick={() => void ligar(true)}>
              <CloudSun size={14} /> Ligar clima e ondas
            </PrimaryButton>
          </div>
        </EdenSection>
      ) : (
        <>
          <EdenSection title="Lugares">
            {lugares.length === 0 ? (
              <Empty>Nenhum lugar ainda. Adicione a sua cidade e as praias favoritas abaixo.</Empty>
            ) : (
              <div className="flex flex-wrap gap-1.5 mb-3" role="tablist" aria-label="Lugares">
                {lugares.map((l) => (
                  <span key={l.id} className="inline-flex items-center rounded-full text-xs" style={{ border: '1px solid var(--color-border)', background: l.id === escolhido ? 'var(--color-accent-subtle)' : 'transparent' }}>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={l.id === escolhido}
                      onClick={() => setEscolhido(l.id)}
                      className="pl-3 pr-1 py-1 cursor-pointer"
                      style={{ color: l.id === escolhido ? 'var(--color-accent)' : 'var(--color-text-secondary)' }}
                    >
                      {l.nome} <span style={cor3}>({l.tipo})</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => void tornarPrincipal(l.id).then(carregar)}
                      aria-label={l.principal ? `${l.nome} é o lugar principal` : `Tornar ${l.nome} o lugar principal`}
                      className="px-1 py-1 cursor-pointer"
                      style={{ color: l.principal ? 'var(--color-accent)' : 'var(--color-text-tertiary)' }}
                    >
                      <Star size={11} fill={l.principal ? 'currentColor' : 'none'} />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm(`Apagar ${l.nome}?`)) void apagarLugar(l.id).then(carregar);
                      }}
                      aria-label={`Apagar ${l.nome}`}
                      className="pl-1 pr-2 py-1 cursor-pointer"
                      style={cor3}
                    >
                      <Trash2 size={11} />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <AdicionarLugar onAdicionado={() => void carregar()} />
          </EdenSection>

          {atual && (
            <EdenSection
              title={atual.nome}
              aside={
                <GhostButton onClick={() => void verPrevisao(atual.id, true)} disabled={carregando}>
                  <RefreshCw size={12} /> Atualizar
                </GhostButton>
              }
            >
              {!previsao ? (
                <Empty>{carregando ? 'Buscando a previsão…' : 'Sem previsão agora.'}</Empty>
              ) : (
                <div className="flex flex-col gap-3">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {previsao.dias.map((d) => (
                      <div key={d.dia} className="rounded-lg px-3 py-2 text-xs" style={{ border: '1px solid var(--color-border)' }}>
                        <div className="font-medium" style={{ color: 'var(--color-text)' }}>
                          {rotuloDia(d.dia)} · {descricaoTempo(d.codigo)}
                        </div>
                        <div style={cor2}>
                          {numero(d.min)}–{numero(d.max)} °C · chuva {numero(d.chuva_prob)}% ({numero(d.chuva_mm, 1)} mm)
                        </div>
                        <div style={cor2}>
                          Vento até {nos(d.vento_kmh) ?? '–'} nós, rajadas {nos(d.rajada_kmh) ?? '–'} · de {rumo(d.vento_dir)}
                        </div>
                      </div>
                    ))}
                  </div>
                  <Tabela previsao={previsao} />
                  <p className="text-[11px]" style={cor3}>
                    De 3 em 3 horas, na hora local do lugar. {atual.tipo === 'praia' && !previsao.mar ? 'Sem dados de ondas para este ponto (talvez longe do mar). ' : ''}
                    Atualizado às {new Date(previsao.atualizado_em).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}.
                    Dados:{' '}
                    <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer" className="underline">
                      {fonte}
                    </a>
                    .
                  </p>
                </div>
              )}
            </EdenSection>
          )}

          <div>
            <GhostButton onClick={() => void ligar(false)}>Desligar clima e ondas</GhostButton>
          </div>
        </>
      )}
    </EdenPage>
  );
}
