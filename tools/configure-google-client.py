#!/usr/bin/python3
"""Prepare a private local maintainer Google Desktop config; never authenticates."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
import google_oauth


def _target(config_home=None):
    target=google_oauth.private_config_path(config_home)
    if target.resolve().is_relative_to(REPO):raise ValueError('Configuração privada deve ficar fora do repositório.')
    return target


def check(*,config_home=None):
    target=_target(config_home)
    google_oauth.read_client_config(target,private=True,required_client_id=google_oauth.DEFAULT_CLIENT_ID)
    return True


def configure(source,*,config_home=None,replace=False):
    if type(replace) is not bool:raise ValueError('Confirmação de substituição inválida.')
    source=Path(source).expanduser().absolute()
    if source.resolve().is_relative_to(REPO):raise ValueError('Mova o JSON do cliente Desktop para fora do repositório antes de configurar.')
    config=google_oauth.read_client_config(source,required_client_id=google_oauth.DEFAULT_CLIENT_ID)
    if not config.get('client_secret'):raise ValueError('JSON Desktop incompleto; client_secret fornecido pelo mantenedor é necessário.')
    target=_target(config_home)
    original=None
    if os.path.lexists(target):
        existing=google_oauth.read_client_config(target,private=True,required_client_id=google_oauth.DEFAULT_CLIENT_ID)
        if existing==config:
            target.parent.chmod(0o700)
            return target
        if not replace:raise FileExistsError('Configuração privada já existe; confirme a troca com --replace.')
        info=target.lstat();original=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    target.parent.chmod(0o700)
    # Recheck ancestry after creation, before writing any secret bytes.
    if target.resolve()!=target:raise ValueError('Destino da configuração vinculada recusado.')
    fd,temporary=tempfile.mkstemp(prefix='.google-client-',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            os.fchmod(stream.fileno(),0o600)
            json.dump({'installed':config},stream,ensure_ascii=False)
            stream.flush();os.fsync(stream.fileno())
        if original is None:
            os.link(temporary,target)
        else:
            info=target.lstat()
            if (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)!=original:raise FileExistsError('Configuração mudou durante preparação; existente preservada.')
            os.replace(temporary,target)
        directory=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:Path(temporary).unlink(missing_ok=True)
    check(config_home=config_home)
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--from-json',type=Path)
    action.add_argument('--check',action='store_true')
    parser.add_argument('--replace',action='store_true',help='Confirma troca de uma configuração privada existente.')
    args=parser.parse_args()
    if args.check:
        if args.replace:parser.error('--replace exige --from-json')
        check();print('GOOGLE_CLIENT_CONFIG_OK — configuração privada válida.')
    else:
        configure(args.from_json,replace=args.replace)
        print('GOOGLE_CLIENT_CONFIG_OK — configuração privada preparada; reabra a agenda e use Entrar com Google.')
    print('Nenhum login foi realizado; nenhum grant existente foi alterado.')


if __name__=='__main__':
    try:main()
    except FileExistsError:
        raise SystemExit('CONFIGURACAO_NAO_CONFIRMADA — configuração existente preservada; use --replace somente para confirmar a troca.') from None
    except Exception:
        # Do not print parser/provider exceptions containing file contents/values.
        raise SystemExit('CONFIGURACAO_NAO_CONFIRMADA — confira o JSON Desktop matching, permissões e destino; nenhum valor foi exibido.') from None
