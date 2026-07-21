-- ==========================================================================
-- Schema do app de ingestão de estoque de fornecedores (SQLite)
--
-- Modelo de identidade (definido com os arquivos reais):
--   * A "fonte" (fornecedor) é identificada pela CHAVE ESTÁVEL do nome do
--     arquivo — sem "Cópia de", sem extensão e SEM a data/período. Dois nomes
--     que diferem em algo além da data são fontes diferentes.
--   * A data/período é guardada à parte e serve para recência: a mesma fonte
--     com data mais nova substitui atomicamente o estoque anterior dela.
--   * A empresa (razão social/CNPJ do conteúdo) e a marca do item são
--     atributos capturados para busca — não são a chave.
-- ==========================================================================

PRAGMA foreign_keys = ON;

-- ==========================================================================
-- FORNECEDORES (fontes) — 1 por chave estável de nome de arquivo
-- ==========================================================================
CREATE TABLE IF NOT EXISTS fornecedores (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_canonico TEXT NOT NULL,                 -- rótulo de exibição (ex: "NTN STOCK LIST")
    slug          TEXT NOT NULL UNIQUE,          -- chave estável (nome sem ruído/data) — identidade
    empresa_fonte TEXT,                          -- razão social do conteúdo (ex: RODOMAQ ROLAMENTOS LTDA)
    cnpj          TEXT,                          -- CNPJ, se aparecer no conteúdo
    ativo         INTEGER NOT NULL DEFAULT 1,
    criado_em     TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ==========================================================================
-- FORNECEDOR_ALIASES — variações do nome da MESMA fonte (typo, com/sem
-- "Cópia de", datas diferentes) apontam para a mesma fonte. Guarda histórico.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS fornecedor_aliases (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    fornecedor_id     INTEGER NOT NULL REFERENCES fornecedores(id) ON DELETE CASCADE,
    alias_normalizado TEXT NOT NULL UNIQUE,      -- nome de arquivo normalizado já visto
    origem            TEXT,                       -- 'arquivo' | 'conteudo'
    visto_em          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_alias_forn ON fornecedor_aliases(fornecedor_id);

-- ==========================================================================
-- ESTOQUE — substituído por completo a cada sincronização da fonte.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS estoque (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    fornecedor_id        INTEGER NOT NULL REFERENCES fornecedores(id) ON DELETE CASCADE,
    codigo_fornecedor    TEXT,                    -- código do item na fonte (ex: 016431, E001567)
    material_original    TEXT NOT NULL,           -- descrição exatamente como veio
    material_normalizado TEXT NOT NULL,           -- descrição normalizada (busca)
    marca                TEXT,                    -- marca do item (SKF, FAG, NTN...)
    marca_normalizada    TEXT,                    -- marca normalizada (busca)
    quantidade           NUMERIC,                 -- estoque disponível
    unidade              TEXT,                    -- pç, un, kg... (rolamentos: normalmente peças)
    data_referencia      TEXT,                    -- período do arquivo (ex: "2026-05")
    arquivo_origem       TEXT NOT NULL,           -- nome do arquivo de origem
    atualizado_em        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_estoque_forn   ON estoque(fornecedor_id);
CREATE INDEX IF NOT EXISTS idx_estoque_mat    ON estoque(material_normalizado);
CREATE INDEX IF NOT EXISTS idx_estoque_marca  ON estoque(marca_normalizada);
CREATE INDEX IF NOT EXISTS idx_estoque_codigo ON estoque(codigo_fornecedor);

-- ==========================================================================
-- INGESTOES — log/auditoria de cada arquivo processado.
-- ==========================================================================
CREATE TABLE IF NOT EXISTS ingestoes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    fornecedor_id  INTEGER REFERENCES fornecedores(id),
    arquivo        TEXT NOT NULL,
    drive_file_id  TEXT,                          -- id do arquivo no Drive (se veio de lá)
    hash_arquivo   TEXT,                          -- SHA-256 do conteúdo (evita reprocessar idêntico)
    periodo        TEXT,                          -- data/período detectado no arquivo/nome
    status         TEXT NOT NULL,                 -- 'sucesso'|'erro'|'parcial'|'ignorado'
    erro           TEXT,
    qtd_registros  INTEGER DEFAULT 0,
    iniciado_em    TEXT NOT NULL DEFAULT (datetime('now')),
    finalizado_em  TEXT
);
CREATE INDEX IF NOT EXISTS idx_ingest_forn ON ingestoes(fornecedor_id);
CREATE INDEX IF NOT EXISTS idx_ingest_arq  ON ingestoes(arquivo);
