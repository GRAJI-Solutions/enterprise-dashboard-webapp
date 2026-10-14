PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dados_profissionais (
    id_dados_profissionais INTEGER PRIMARY KEY AUTOINCREMENT,
    cargo TEXT NOT NULL CHECK (length(trim(cargo)) > 0),
    contrato TEXT NOT NULL CHECK (length(contrato) > 0),
    turno TEXT CHECK (turno IN ('Manhã', 'Tarde', 'Noite', 'Integral')),
    carga_horaria_semanal_contrato INTEGER CHECK (carga_horaria_semanal_contrato > 0 AND carga_horaria_semanal_contrato <= 44),
    departamento TEXT NOT NULL CHECK (length(departamento) > 0),
    data_admissao TEXT NOT NULL 
        CHECK (
            length(data_admissao) = 10 
            AND data_admissao GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND strftime('%Y-%m-%d', data_admissao) IS NOT NULL
        )
);

CREATE TABLE IF NOT EXISTS login (
    id_login INTEGER PRIMARY KEY AUTOINCREMENT,
    registro TEXT NOT NULL UNIQUE
        CHECK (length(trim(registro)) > 0),
    senha TEXT NOT NULL CHECK (length(senha) > 1),
    nivel_acesso TEXT NOT NULL
        CHECK (length(trim(nivel_acesso)) > 0)
);

CREATE TABLE IF NOT EXISTS colaborador (
    id_colaborador INTEGER PRIMARY KEY AUTOINCREMENT,
    cpf TEXT NOT NULL UNIQUE
        CHECK (length(cpf) = 11 AND cpf NOT GLOB '*[^0-9]*'),
    nome_completo TEXT NOT NULL CHECK (length(trim(nome_completo)) > 0),
    genero TEXT NOT NULL CHECK (genero IN ('M', 'F', 'Outro')),
	data_nascimento TEXT NOT NULL
    	CHECK (length(data_nascimento) = 10 AND data_nascimento GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' AND strftime('%Y-%m-%d', data_nascimento) IS NOT NULL),
    id_dados_profissionais INTEGER NOT NULL UNIQUE,
    id_login INTEGER NOT NULL UNIQUE,
    FOREIGN KEY (id_dados_profissionais) REFERENCES dados_profissionais(id_dados_profissionais) ON DELETE RESTRICT,
	FOREIGN KEY (id_login) REFERENCES login(id_login) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS endereco (
    id_endereco INTEGER PRIMARY KEY AUTOINCREMENT,
    cep TEXT NOT NULL CHECK (length(cep) = 8 AND cep NOT GLOB '*[^0-9]*'),
    estado TEXT NOT NULL CHECK (length(estado) = 2),
    cidade TEXT NOT NULL,
    bairro TEXT NOT NULL,
    rua TEXT NOT NULL,
    numero TEXT NOT NULL,
    complemento TEXT,
    id_colaborador INTEGER NOT NULL,
    FOREIGN KEY(id_colaborador) REFERENCES colaborador(id_colaborador) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS contato (
    id_contato INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_celular TEXT NOT NULL CHECK (length(numero_celular) = 11 AND numero_celular NOT GLOB '*[^0-9]*'),
    id_colaborador INTEGER NOT NULL,
    FOREIGN KEY(id_colaborador) REFERENCES colaborador(id_colaborador) ON DELETE CASCADE,
    UNIQUE (id_colaborador, numero_celular)
);

CREATE TABLE IF NOT EXISTS historico_salarial (
    id_historico_salarial INTEGER PRIMARY KEY AUTOINCREMENT,
    valor NUMERIC NOT NULL CHECK (valor > 0),
    data_inicio TEXT NOT NULL 
        CHECK (
            length(data_inicio) = 10 
            AND data_inicio GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND strftime('%Y-%m-%d', data_inicio) IS NOT NULL
        ),
    data_fim TEXT 
        CHECK (
            data_fim IS NULL OR (
                length(data_fim) = 10 
                AND data_fim GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
                AND strftime('%Y-%m-%d', data_fim) IS NOT NULL
                AND data_fim >= data_inicio
            )
        ),
    colaborador_id_colaborador INTEGER NOT NULL,
    FOREIGN KEY(colaborador_id_colaborador) REFERENCES colaborador(id_colaborador) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS escala (
    id_escala INTEGER PRIMARY KEY AUTOINCREMENT,
    dia_semana TEXT NOT NULL CHECK (dia_semana IN ('Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo')),
	hora_entrada TEXT CHECK (hora_entrada IS NULL OR hora_entrada GLOB '[0-1][0-9]:[0-5][0-9]' OR hora_entrada GLOB '2[0-3]:[0-5][0-9]'),
	inicio_intervalo TEXT CHECK (inicio_intervalo IS NULL OR inicio_intervalo GLOB '[0-1][0-9]:[0-5][0-9]' OR inicio_intervalo GLOB '2[0-3]:[0-5][0-9]'),
	fim_intervalo TEXT CHECK (fim_intervalo IS NULL OR fim_intervalo GLOB '[0-1][0-9]:[0-5][0-9]' OR fim_intervalo GLOB '2[0-3]:[0-5][0-9]'),
	hora_saida TEXT CHECK (hora_saida IS NULL OR hora_saida GLOB '[0-1][0-9]:[0-5][0-9]' OR hora_saida GLOB '2[0-3]:[0-5][0-9]'),
    id_colaborador INTEGER NOT NULL,
    FOREIGN KEY(id_colaborador) REFERENCES colaborador(id_colaborador) ON DELETE CASCADE,
    UNIQUE (id_colaborador, dia_semana)
);

CREATE TABLE IF NOT EXISTS ferias (
    id_ferias INTEGER PRIMARY KEY AUTOINCREMENT,
    data_inicio TEXT NOT NULL 
        CHECK (length(data_inicio) = 10 AND data_inicio GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' AND strftime('%Y-%m-%d', data_inicio) IS NOT NULL),
    data_fim TEXT NOT NULL 
        CHECK (length(data_fim) = 10 AND data_fim GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' AND strftime('%Y-%m-%d', data_fim) IS NOT NULL AND data_fim >= data_inicio),
    data_solicitacao TEXT NOT NULL 
        CHECK (length(data_solicitacao) = 10 AND data_solicitacao GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' AND strftime('%Y-%m-%d', data_solicitacao) IS NOT NULL),
    status TEXT NOT NULL CHECK (status IN ('Pendente', 'Aprovada', 'Rejeitada')),
    dias_ferias_disponiveis INTEGER CHECK (dias_ferias_disponiveis >= 0),
    dias_solicitados INTEGER CHECK (dias_solicitados > 0 AND dias_solicitados <= 30),
    id_colaborador INTEGER NOT NULL,
    FOREIGN KEY(id_colaborador) REFERENCES colaborador(id_colaborador) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ponto (
    id_ponto INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL 
        CHECK (length(data) = 10 AND data GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' AND strftime('%Y-%m-%d', data) IS NOT NULL),
	hora_entrada TEXT CHECK (hora_entrada IS NULL OR hora_entrada GLOB '[0-1][0-9]:[0-5][0-9]' OR hora_entrada GLOB '2[0-3]:[0-5][0-9]'),
	inicio_intervalo TEXT CHECK (inicio_intervalo IS NULL OR inicio_intervalo GLOB '[0-1][0-9]:[0-5][0-9]' OR inicio_intervalo GLOB '2[0-3]:[0-5][0-9]'),
	fim_intervalo TEXT CHECK (fim_intervalo IS NULL OR fim_intervalo GLOB '[0-1][0-9]:[0-5][0-9]' OR fim_intervalo GLOB '2[0-3]:[0-5][0-9]'),
	hora_saida TEXT CHECK (hora_saida IS NULL OR hora_saida GLOB '[0-1][0-9]:[0-5][0-9]' OR hora_saida GLOB '2[0-3]:[0-5][0-9]'),
    id_colaborador INTEGER NOT NULL,
    FOREIGN KEY(id_colaborador) REFERENCES colaborador(id_colaborador) ON DELETE CASCADE,
    UNIQUE (id_colaborador, data)
);

CREATE INDEX IF NOT EXISTS idx_ferias_colaborador
    ON ferias (id_colaborador);

CREATE INDEX IF NOT EXISTS idx_historico_salarial_colaborador
    ON historico_salarial (colaborador_id_colaborador);

CREATE INDEX IF NOT EXISTS idx_endereco_colaborador
    ON endereco (id_colaborador);