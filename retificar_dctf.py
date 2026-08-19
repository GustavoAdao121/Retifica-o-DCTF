# -*- coding: utf-8 -*-
"""
Retificacao de DCTF Mensal (.dec) - altera valor de debito (R10) e de pagamento (R11)
e recalcula os hashcodes CRC32 de cada registro + o CRC32 global do H0.

ATENCAO: o hashcode do H0 (pos 365-374) ainda NAO foi decifrado. Ver README_RETIFICACAO.md.
"""
import sys, zlib, argparse

ENC = "latin-1"

# posicoes 1-based (inicio, fim)
POS = {
    "H0_TIPO_DECL":      (21, 21),    # 0=Original 1=Retificadora
    "H0_CRC_GLOBAL":     (102, 111),  # CRC32 da concatenacao dos registros (sem H0, sem CRLF)
    "H0_TOTAL_DEBITOS":  (171, 184),  # soma dos valores de debito (R10 campo 15)
    "H0_HASH":           (365, 374),
    "R01_RETIFICADORA":  (41, 41),
    "R01_NUM_RECIBO":    (42, 53),
    "R10_COD_RECEITA":   (35, 40),
    "R10_VALOR_DEBITO":  (71, 84),
    "R11_COD_RECEITA":   (35, 40),
    "R11_VLR_PRINCIPAL": (122, 135),
    "R11_VLR_MULTA":     (136, 149),
    "R11_VLR_JUROS":     (150, 163),
    "R11_VLR_PAGO":      (164, 177),
}

def get(line, key):
    a, b = POS[key]
    return line[a-1:b]

def put(line, key, value):
    a, b = POS[key]
    size = b - a + 1
    v = str(value)
    if len(v) != size:
        raise ValueError("campo %s espera %d chars, recebeu %d (%r)" % (key, size, len(v), v))
    return line[:a-1] + v + line[b:]

def brl_to_field(valor_reais, size=14):
    """'1174.48' ou 1174.48 -> '00000000117448'"""
    cent = int(round(float(str(valor_reais).replace(",", ".")) * 100))
    return str(cent).zfill(size)

def field_to_brl(v):
    return int(v) / 100.0

def crc10(s):
    return "%010d" % zlib.crc32(s.encode(ENC))

def ler(path):
    data = open(path, "rb").read().decode(ENC)
    return [l for l in data.split("\r\n") if l.strip()]

def recalcular(lines):
    """Recalcula hash de cada registro (nao-H0) e o CRC global no H0."""
    out = [lines[0]]
    for l in lines[1:]:
        out.append(l[:-10] + crc10(l[:-10]))
    # totalizador de debitos no H0
    total = sum(int(get(l, "R10_VALOR_DEBITO")) for l in out if l.startswith("R10"))
    h0 = out[0]
    h0 = put(h0, "H0_TOTAL_DEBITOS", str(total).zfill(14))
    # CRC global tem de ser calculado por ultimo
    h0 = put(h0, "H0_CRC_GLOBAL", crc10("".join(out[1:])))
    out[0] = h0
    return out

def validar(lines):
    erros = []
    for i, l in enumerate(lines[1:], start=2):
        esperado = crc10(l[:-10])
        if l[-10:] != esperado:
            erros.append("linha %d (%s): hash %s, esperado %s" % (i, l[:3], l[-10:], esperado))
    esperado_g = crc10("".join(lines[1:]))
    if get(lines[0], "H0_CRC_GLOBAL") != esperado_g:
        erros.append("H0 CRC global: %s, esperado %s" % (get(lines[0], "H0_CRC_GLOBAL"), esperado_g))
    total = sum(int(get(l, "R10_VALOR_DEBITO")) for l in lines if l.startswith("R10"))
    if get(lines[0], "H0_TOTAL_DEBITOS") != str(total).zfill(14):
        erros.append("H0 total debitos: %s, esperado %s" % (get(lines[0], "H0_TOTAL_DEBITOS"), str(total).zfill(14)))
    return erros

def listar(lines):
    print("%-4s %-10s %-16s %16s" % ("REG", "COD.REC", "CAMPO", "VALOR R$"))
    print("-" * 52)
    for l in lines:
        if l.startswith("R10"):
            print("%-4s %-10s %-16s %16.2f" % ("R10", get(l, "R10_COD_RECEITA"), "debito",
                  field_to_brl(get(l, "R10_VALOR_DEBITO"))))
        elif l.startswith("R11"):
            c = get(l, "R11_COD_RECEITA")
            print("%-4s %-10s %-16s %16.2f" % ("R11", c, "principal", field_to_brl(get(l, "R11_VLR_PRINCIPAL"))))
            print("%-4s %-10s %-16s %16.2f" % ("", "", "multa", field_to_brl(get(l, "R11_VLR_MULTA"))))
            print("%-4s %-10s %-16s %16.2f" % ("", "", "juros", field_to_brl(get(l, "R11_VLR_JUROS"))))
            print("%-4s %-10s %-16s %16.2f" % ("", "", "pago", field_to_brl(get(l, "R11_VLR_PAGO"))))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("arquivo")
    p.add_argument("-o", "--saida")
    p.add_argument("--listar", action="store_true")
    p.add_argument("--validar", action="store_true")
    p.add_argument("--codigo", help="codigo da receita (6 pos, ex 058806)")
    p.add_argument("--debito", help="novo valor do debito em reais, ex 250.00")
    p.add_argument("--principal", help="novo valor do principal pago")
    p.add_argument("--multa", help="novo valor da multa")
    p.add_argument("--juros", help="novo valor dos juros")
    p.add_argument("--pago", help="novo valor pago do debito")
    p.add_argument("--recibo", help="numero do recibo da DCTF a retificar (12 digitos)")
    p.add_argument("--marcar-retificadora", action="store_true")
    a = p.parse_args()

    lines = ler(a.arquivo)

    if a.listar:
        listar(lines); return
    if a.validar:
        e = validar(lines)
        print("OK: todos os hashes conferem" if not e else "\n".join(e)); return

    if a.marcar_retificadora:
        lines[0] = put(lines[0], "H0_TIPO_DECL", "1")
        for i, l in enumerate(lines):
            if l.startswith("R01"):
                lines[i] = put(l, "R01_RETIFICADORA", "1")
    if a.recibo:
        for i, l in enumerate(lines):
            if l.startswith("R01"):
                lines[i] = put(l, "R01_NUM_RECIBO", a.recibo.zfill(12))

    if a.codigo:
        alt = 0
        for i, l in enumerate(lines):
            if l.startswith("R10") and get(l, "R10_COD_RECEITA") == a.codigo and a.debito:
                lines[i] = put(l, "R10_VALOR_DEBITO", brl_to_field(a.debito)); alt += 1
            elif l.startswith("R11") and get(l, "R11_COD_RECEITA") == a.codigo:
                nl = l
                if a.principal: nl = put(nl, "R11_VLR_PRINCIPAL", brl_to_field(a.principal))
                if a.multa:     nl = put(nl, "R11_VLR_MULTA", brl_to_field(a.multa))
                if a.juros:     nl = put(nl, "R11_VLR_JUROS", brl_to_field(a.juros))
                if a.pago:      nl = put(nl, "R11_VLR_PAGO", brl_to_field(a.pago))
                if nl != l: lines[i] = nl; alt += 1
        print("registros alterados: %d" % alt)

    lines = recalcular(lines)

    saida = a.saida or (a.arquivo.replace(".dec", "-ALTERADO.dec"))
    open(saida, "wb").write(("\r\n".join(lines) + "\r\n").encode(ENC))
    print("gravado: %s" % saida)
    print("AVISO: hashcode do H0 (pos 365-374) NAO recalculado - algoritmo desconhecido.")

if __name__ == "__main__":
    main()
