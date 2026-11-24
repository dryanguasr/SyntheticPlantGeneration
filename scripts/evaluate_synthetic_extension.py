"""Same frozen evaluation, with an explicit report of the authorized size mismatch."""
import sys
import types
from augmentation_pilot import ROOT,REPO,read,write,sha
import report_augmentation_campaign as base_report
import evaluate_augmentation_campaign as evaluator


def report():
    staging=ROOT/'report_staging'
    (staging/'docs/reports').mkdir(parents=True,exist_ok=True)
    base_report.REPO=staging
    base_report.report()
    source=staging/'docs/reports/piloto_aumentacion_geometrica_2026-10-22.md'
    text=source.read_text(encoding='utf-8')
    text=text.replace('# Piloto geométrico de aumentación — 22 de octubre de 2026',
        '# Piloto exploratorio con aumentación sintética — 22 de octubre de 2026')
    lines=text.splitlines()
    for i,line in enumerate(lines):
        if line.startswith('Criterio revisado por instrucción del usuario'):
            lines[i]='El usuario autorizó expresamente entrenar con las imágenes disponibles pese al incumplimiento de tamaños. Se conservaron los diagnósticos originales: estas mezclas NO son geométricamente validadas. Densidad y tamaños se reportan como limitaciones; todas las etiquetas visibles permanecen.'
    lines += ['', '## Desajuste sintético y proporciones efectivas', '',
        'Banco: 389 imágenes disponibles, incluidas las 12 vistas de calibración, procedentes exclusivamente de plantas train. Las cantidades se anidan sobre el orden previo, sin usar test para elegirlas. No hay nuevos renders.', '',
        'Las proporciones son sintéticas/reales, no porcentaje del total. Para 461 reales se usan 115, 230 y 389 sintéticas: 24,95 %, 49,89 % y 84,38 %; no se inventan las 72 imágenes faltantes para llegar a 100 %. Para 210 reales: 52, 105 y 210; para 125: 31, 62 y 125.', '',
        'La sobreabundancia de instancias diminutas, la apariencia simplificada de fondos/hojas, las oclusiones y las cuatro plantas de origen limitan la interpretación. Una mejora o caída mide el efecto de este banco disponible, no el de un generador geométricamente emparejado ni generalización externa.', '',
        'Los controles reales se reutilizan por hash: mismo modelo inicial, pasos, semillas, optimizador, resolución y receta clásica. El presupuesto de 24 horas original se mantiene. Las cifras intermedias de validación ya se habían consultado antes de esta extensión solicitada por el usuario; se conserva su carácter exploratorio.', '']
    destination=REPO/'docs/reports/piloto_aumentacion_sintetica_exploratoria_2026-10-22.md'
    destination.write_text('\n'.join(lines),encoding='utf-8')
    write(ROOT/'report.json',dict(path=str(destination),sha256=sha(destination),size_gate_waived=True))


if __name__=='__main__':
    replacement=types.ModuleType('report_augmentation_campaign');replacement.report=report
    sys.modules['report_augmentation_campaign']=replacement
    evaluator.main()
