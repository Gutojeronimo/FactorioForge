"""Read save metadata without loading or changing the world."""
import json
import re
import shutil
import struct
import zipfile
from pathlib import Path


def read(path):
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith('/level-init.dat')]
        if len(names) != 1:
            raise ValueError('O ZIP não contém um mundo Factorio reconhecido.')
        with archive.open(names[0]) as source:
            data = source.read(2 * 1024 * 1024)
    offset = 0

    def take(size):
        nonlocal offset
        value = data[offset:offset + size]
        if len(value) != size:
            raise ValueError('Cabeçalho do save incompleto.')
        offset += size
        return value

    def number(size=4, compact=False):
        if compact:
            first = take(1)[0]
            if first != 255:
                return first
        return int.from_bytes(take(size), 'little')

    def string():
        size = number(compact=True)
        if size > 10000:
            raise ValueError('Formato do cabeçalho do save não suportado.')
        return take(size).decode('utf-8')

    version = struct.unpack('<4H', take(8))
    if version[0] not in (1, 2):
        raise ValueError('Versão do save não suportada.')
    take(1)
    campaign, scenario, base = string(), string(), string()
    take(3)
    string()
    take(4)
    for _ in range(3):
        number(2, True)
    take(4 if version[0] >= 2 else 2)
    take(1 + (4 if version[0] >= 2 else 0))
    count = number(compact=True)
    if count < 1 or count > 3000:
        raise ValueError('Lista de mods inválida no save.')
    mods = []
    for _ in range(count):
        name = string()
        if not re.fullmatch(r'[A-Za-z0-9_. -]+', name) or name in ('.', '..'):
            raise ValueError('Nome de mod inválido no save.')
        mod_version = '.'.join(str(number(2, True)) for _ in range(3))
        crc = number()
        mods.append({'name': name, 'version': mod_version, 'enabled': True, 'crc': crc})
    if base != 'base' or not any(m['name'] == 'base' for m in mods):
        raise ValueError('Cabeçalho do save não reconhecido.')
    return {'path': str(path.resolve()), 'name': path.stem, 'game_version': '.'.join(map(str, version[:3])), 'mods': mods, 'scenario': scenario or campaign}


def prepare(info, source, data_dir, destination, allow_versions=False):
    source, data_dir, destination = Path(source), Path(data_dir), Path(destination)
    copies, missing = [], []
    for mod in info['mods']:
        name, version = mod['name'], mod['version']
        if (data_dir / name / 'info.json').is_file():
            installed = json.loads((data_dir / name / 'info.json').read_text(encoding='utf-8'))
            if installed['version'] != version and not (allow_versions and installed['version'].split('.')[:2] == version.split('.')[:2]):
                missing.append(name + ' ' + version + ' (versão do jogo incompatível)')
            continue
        archive = source / f'{name}_{version}.zip'
        if archive.is_file():
            copies.append((archive, archive.name))
            continue
        folder = source / name
        try:
            if json.loads((folder / 'info.json').read_text(encoding='utf-8'))['version'] == version:
                copies.append((folder, name))
                continue
        except (OSError, ValueError, KeyError):
            pass
        if allow_versions:
            found = False
            for candidate in sorted(source.glob(name + '_*.zip'), reverse=True):
                try:
                    with zipfile.ZipFile(candidate) as z:
                        member = next(n for n in z.namelist() if n.endswith('/info.json') and n.count('/') <= 1)
                        version_found = json.loads(z.read(member)).get('version', '')
                    if version_found.split('.')[:2] == version.split('.')[:2]:
                        copies.append((candidate, candidate.name)); found=True; break
                except (OSError, ValueError, StopIteration, KeyError):
                    continue
            if found:
                continue
        missing.append(name + ' ' + version)
    if missing:
        raise ValueError('Mods do save ausentes na pasta selecionada: ' + ', '.join(missing))
    destination.mkdir(parents=True, exist_ok=True)
    for origin, name in copies:
        target = destination / name
        if origin.is_dir():
            shutil.copytree(origin, target, dirs_exist_ok=True)
        elif not target.is_file() or target.stat().st_size != origin.stat().st_size:
            shutil.copy2(origin, target)
    (destination / 'mod-list.json').write_text(json.dumps({'mods': [{k: m[k] for k in ('name', 'version', 'enabled')} for m in info['mods']]}, indent=2), encoding='utf-8')
    # Factorio's sync step below reads the startup settings from the save itself.
    return destination
