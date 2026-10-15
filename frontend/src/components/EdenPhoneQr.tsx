// Éden: QR code para conectar um celular. O link leva o endereço do Éden e a
// chave de acesso; o celular abre, guarda a chave e já entra.
import { useMemo } from 'react';
import { qrcodegen } from '../lib/vendor/qrcodegen';

interface Props {
  text: string;
  size?: number;
}

export function EdenPhoneQr({ text, size = 220 }: Props) {
  const qr = useMemo(
    () => qrcodegen.QrCode.encodeText(text, qrcodegen.QrCode.Ecc.MEDIUM),
    [text],
  );
  const border = 4;
  const dim = qr.size + border * 2;
  const path = useMemo(() => {
    const parts: string[] = [];
    for (let y = 0; y < qr.size; y++) {
      for (let x = 0; x < qr.size; x++) {
        if (qr.getModule(x, y)) parts.push(`M${x + border},${y + border}h1v1h-1z`);
      }
    }
    return parts.join('');
  }, [qr]);

  // Sempre preto no branco (o tema escuro atrapalha a leitura da câmera).
  return (
    <svg
      role="img"
      aria-label="QR code para conectar um celular ao Éden"
      viewBox={`0 0 ${dim} ${dim}`}
      width={size}
      height={size}
      shapeRendering="crispEdges"
      style={{ background: '#ffffff', borderRadius: 8 }}
    >
      <rect width={dim} height={dim} fill="#ffffff" />
      <path d={path} fill="#000000" />
    </svg>
  );
}
