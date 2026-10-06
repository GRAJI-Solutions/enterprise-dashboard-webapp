PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Colaborador (
    id_colaborador   INTEGER PRIMARY KEY AUTOINCREMENT,
    cpf              TEXT    NOT NULL UNIQUE
                             CHECK (length(cpf) = 11 AND cpf NOT GLOB '*[^0-9]*'),
    nome_completo    TEXT    NOT NULL,
    genero           TEXT,
    data_nascimento  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS Escala_Semanal (
    id_escala         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_colaborador    INTEGER NOT NULL,
    dia_semana        TEXT    NOT NULL
                              CHECK (dia_semana IN ('Segunda','Terça','Quarta','Quinta',
                                                    'Sexta','Sábado','Domingo')),
    hora_entrada      TEXT    NOT NULL,
    inicio_intervalo  TEXT,
    fim_intervalo     TEXT,
    hora_saida        TEXT    NOT NULL,
    UNIQUE (id_colaborador, dia_semana),
    FOREIGN KEY (id_colaborador) REFERENCES Colaborador (id_colaborador)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Ponto (
    id_ponto          INTEGER PRIMARY KEY AUTOINCREMENT,
    id_colaborador    INTEGER NOT NULL,
    data              TEXT    NOT NULL,
    hora_entrada      TEXT    DEFAULT CURRENT_TIMESTAMP,
    inicio_intervalo  TEXT    DEFAULT CURRENT_TIMESTAMP,
    fim_intervalo     TEXT    DEFAULT CURRENT_TIMESTAMP,
    hora_saida        TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_colaborador, data),
    FOREIGN KEY (id_colaborador) REFERENCES Colaborador (id_colaborador)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Ferias (
    id_ferias                INTEGER PRIMARY KEY AUTOINCREMENT,
    id_colaborador           INTEGER NOT NULL,
    data_inicio              TEXT    NOT NULL,
    data_fim                 TEXT    NOT NULL,
    data_solicitacao         TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status                   TEXT    NOT NULL DEFAULT 'Pendente',
    dias_ferias_disponiveis  INTEGER NOT NULL CHECK (dias_ferias_disponiveis >= 0),
    dias_solicitados         INTEGER NOT NULL CHECK (dias_solicitados > 0),
    CHECK (data_fim >= data_inicio),
    FOREIGN KEY (id_colaborador) REFERENCES Colaborador (id_colaborador)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Login (
    id_usuario      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_colaborador  INTEGER NOT NULL,
    registro        INTEGER NOT NULL UNIQUE,
    senha           TEXT    NOT NULL,
    nivel_acesso    INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (id_colaborador) REFERENCES Colaborador (id_colaborador)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Dados_Profissionais (
    id_dados_profissionais          INTEGER PRIMARY KEY AUTOINCREMENT,
    id_colaborador                  INTEGER NOT NULL,
    cargo                           TEXT    NOT NULL,
    contrato                        TEXT    NOT NULL,
    turno                           TEXT,
    carga_horaria_semanal_contrato  INTEGER NOT NULL
                                            CHECK (carga_horaria_semanal_contrato > 0),
    departamento                    TEXT    NOT NULL,
    data_admissao                   TEXT    NOT NULL,
    FOREIGN KEY (id_colaborador) REFERENCES Colaborador (id_colaborador)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Historico_Salarial (
    id_historico    INTEGER PRIMARY KEY AUTOINCREMENT,
    id_colaborador  INTEGER NOT NULL,
    valor           REAL    NOT NULL CHECK (valor >= 0),
    data_inicio     TEXT    NOT NULL,
    data_fim        TEXT,
    CHECK (data_fim IS NULL OR data_fim >= data_inicio),
    FOREIGN KEY (id_colaborador) REFERENCES Colaborador (id_colaborador)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Endereco (
    id_endereco     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_colaborador  INTEGER NOT NULL,
    cep             TEXT    NOT NULL
                            CHECK (length(cep) = 8 AND cep NOT GLOB '*[^0-9]*'),
    estado          TEXT    NOT NULL,
    cidade          TEXT    NOT NULL,
    bairro          TEXT    NOT NULL,
    rua             TEXT    NOT NULL,
    numero          INTEGER,
    FOREIGN KEY (id_colaborador) REFERENCES Colaborador (id_colaborador)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Contato (
    id_contato      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_colaborador  INTEGER NOT NULL,
    numero_celular  TEXT    NOT NULL
                            CHECK (length(numero_celular) BETWEEN 10 AND 11
                                   AND numero_celular NOT GLOB '*[^0-9]*'),
    FOREIGN KEY (id_colaborador) REFERENCES Colaborador (id_colaborador)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ferias_colaborador               ON Ferias (id_colaborador);
CREATE INDEX IF NOT EXISTS idx_login_colaborador                ON Login (id_colaborador);
CREATE INDEX IF NOT EXISTS idx_dados_profissionais_colaborador  ON Dados_Profissionais (id_colaborador);
CREATE INDEX IF NOT EXISTS idx_historico_salarial_colaborador   ON Historico_Salarial (id_colaborador);
CREATE INDEX IF NOT EXISTS idx_endereco_colaborador             ON Endereco (id_colaborador);
CREATE INDEX IF NOT EXISTS idx_contato_colaborador              ON Contato (id_colaborador);
