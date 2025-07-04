-- Table: public.orcamento

-- DROP TABLE IF EXISTS public.orcamento;

CREATE TABLE IF NOT EXISTS public.orcamento
(
    id integer NOT NULL DEFAULT nextval('orcamento_id_seq'::regclass),
    categoria text COLLATE pg_catalog."default",
    valor_custeio_mensal numeric,
    valor_flutuante_mensal numeric,
    valor_custeio_anual numeric,
    valor_flutuante_anual numeric,
    parcelas_ano_anterior numeric,
    valor_custeio_total numeric,
    valor_flutuante_total numeric,
    ano integer,
    CONSTRAINT orcamento_pkey PRIMARY KEY (id),
    CONSTRAINT unique_categoria_ano UNIQUE (categoria, ano),
    CONSTRAINT chk_valores_nao_negativos CHECK (valor_custeio_mensal >= 0::numeric AND valor_flutuante_mensal >= 0::numeric AND valor_custeio_anual >= 0::numeric AND valor_flutuante_anual >= 0::numeric AND parcelas_ano_anterior >= 0::numeric),
    CONSTRAINT chk_totais_consistentes CHECK (valor_custeio_total = (valor_custeio_anual + 12::numeric * valor_custeio_mensal) AND valor_flutuante_total = (valor_flutuante_anual + 12::numeric * valor_flutuante_mensal))
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.orcamento
    OWNER to postgres;

-- Trigger: valida_categoria_trigger

-- DROP TRIGGER IF EXISTS valida_categoria_trigger ON public.orcamento;

CREATE OR REPLACE TRIGGER valida_categoria_trigger
    BEFORE INSERT OR UPDATE 
    ON public.orcamento
    FOR EACH ROW
    EXECUTE FUNCTION public.valida_categoria();


-- Table: public.transacoes

-- DROP TABLE IF EXISTS public.transacoes;

CREATE TABLE IF NOT EXISTS public.transacoes
(
    id integer NOT NULL DEFAULT nextval('transacoes_id_seq'::regclass),
    data date NOT NULL,
    descricao text COLLATE pg_catalog."default",
    conta character varying(255) COLLATE pg_catalog."default",
    categoria character varying(255) COLLATE pg_catalog."default",
    centro_custo character varying(255) COLLATE pg_catalog."default",
    valor numeric(15,2),
    CONSTRAINT transacoes_pkey PRIMARY KEY (id)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.transacoes
    OWNER to postgres;