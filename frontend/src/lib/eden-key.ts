// Éden: limpa o que a pessoa colou no campo da chave de acesso.
//
// Aceita a chave sozinha, a linha inteira do .env ("OPENJARVIS_API_KEY=oj_sk_…"),
// com espaços ou aspas, e também o caso em que o navegador já tinha preenchido
// uma senha salva no campo e a chave foi colada junto: fica só a última chave
// no formato oj_sk_….
const KEY_PATTERN = /oj_sk_[A-Za-z0-9_-]+/g;

export function normalizeAccessKey(raw: string): string {
  const matches = raw.match(KEY_PATTERN);
  if (matches && matches.length > 0) return matches[matches.length - 1];
  return raw
    .trim()
    .replace(/^OPENJARVIS_API_KEY\s*=\s*/, '')
    .replace(/^["']|["']$/g, '')
    .trim();
}
