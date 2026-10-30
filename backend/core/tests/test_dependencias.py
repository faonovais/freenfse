from importlib.metadata import version

VERSAO_MINIMA_FREEDFE = (0, 3, 0)


def test_freedfe_instalada_na_versao_minima():
    instalada = tuple(int(parte) for parte in version("freedfe").split(".")[:3])

    assert instalada >= VERSAO_MINIMA_FREEDFE


def test_freedfe_expoe_os_pontos_de_entrada_usados_pelo_plano():
    from freedfe.certificado import CertificadoA1
    from freedfe.nfse.fabrica import criar_servico_nfse

    assert callable(criar_servico_nfse)
    assert isinstance(CertificadoA1, type)


def test_extra_nfse_da_freedfe_esta_instalado():
    import lxml.etree
    import reportlab

    assert lxml.etree is not None
    assert reportlab is not None
