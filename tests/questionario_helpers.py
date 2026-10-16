def questionario_payload():
    return {
        "versao": "pre-triagem-v1",
        "versao_aviso": "pre-triagem-privacidade-v1",
        "confirmacoes": ["veracidade", "avaliacao_presencial", "ciencia_privacidade"],
        "respostas": [
            {"id": "peso", "valores": ["70"]},
            {"id": "doacao_anterior", "valores": ["nao"]},
            {"id": "sintomas", "valores": ["nao"]},
            {"id": "tratamento", "valores": ["nao"]},
            {"id": "condicao_saude", "valores": ["nao"]},
            {"id": "medicamentos", "valores": ["nao"]},
            {"id": "vacinas", "valores": ["nao"]},
            {"id": "procedimentos", "valores": ["nenhum"]},
            {"id": "viagens", "valores": ["nao"]},
            {"id": "gestacao", "valores": ["reservado"]},
            {"id": "amamentacao", "valores": ["reservado"]},
            {"id": "parto_aborto", "valores": ["reservado"]},
            {"id": "prep_pep", "valores": ["reservado"]},
            {"id": "exposicoes", "valores": ["reservado"]},
        ],
    }


def publicar_questionario(monkeypatch):
    monkeypatch.setenv("PRIVACIDADE_CONTROLADOR", "Instituicao ficticia de teste")
    monkeypatch.setenv("PRIVACIDADE_CANAL", "privacidade@example.com")
