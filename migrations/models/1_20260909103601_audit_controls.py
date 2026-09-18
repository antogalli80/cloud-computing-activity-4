from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO cloud_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON users, sessions, files TO cloud_app;
GRANT INSERT ON audit_events TO cloud_app;
GRANT SELECT (id) ON audit_events TO cloud_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cloud_app;
CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Audit records are append-only';
END;
$$;
CREATE TRIGGER protect_audit_changes BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_events
FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_mutation();
ALTER TABLE files ADD CONSTRAINT nonnegative_file_size CHECK (size_bytes >= 0);
ALTER TABLE files ADD CONSTRAINT consistent_content_reference CHECK (
 (content_key IS NULL AND sha256 IS NULL AND content_type IS NULL AND size_bytes = 0)
 OR (content_key IS NOT NULL AND sha256 ~ '^[0-9a-f]{64}$' AND content_type IS NOT NULL));
ALTER TABLE audit_events ADD CONSTRAINT valid_audit_outcome CHECK (outcome IN ('success','rejected','failed'));

        """


async def downgrade(db: BaseDBAsyncClient) -> str:
    raise RuntimeError("Security migration is forward-only; restore a verified backup if required.")


MODELS_STATE = (
    "eJztmltz6jYQx78Kw1M6k2aIuaV9I7ceeprQSUjbOZmMR7EX0MRIHEsOoWf47pVkG98Npt"
    "yc4YWBldbW/lay/vLyozqmJljs7BEYw5TcyV/VXys/qgSNQXxJbT+tVNFkErRKA0evlnJg"
    "bk9lRK+M28jgwj5AFgNhMoEZNp5w0UVYiWNZ0kgN0RGTYWByCP7ugM7pEPgIbNHw/CLMmJ"
    "jwAcz/OXnTBxgsMzJkbMp7K7vOZxNlu8TDLuG3qq+84atuUMsZk6D/ZMZHlCwcMOHSOgQC"
    "NuIg78BtR0YgB+gF6wflDjbo4o4y5GPCADkWD0W8IgZDkBQIxWiYinEo7/LzL5pWr7e1Wr"
    "110Wy0282L2oXoq4aUbGrP3YADIO6lFJbub937vgyUijy5CZSGufJBHLleincA2MRDYDwJ"
    "+WqE7HTEgUcMswgujtmHulfOY/ShW0CGfCR+tho5CP/qPFx96TyctBo/RTneey2aapJEA4"
    "KGDTJaHaVQvBYtHI8hnWTUM0bT9FzP/C/rsPUNAdxg7W6Gbg7Nfvfu5rHfuftTjnzM2HdL"
    "Ien0b2SLpqyzmPWkFSO/uEjl727/S0X+rHzr3d8oYpTxoa3uGPTrf6vKMSGHU53QqY7McN"
    "i+2TdFMmkhxnUGQNbIZdz3mM19ZxM+Jlhcbo1cRj13k8kNP/Q+UyIdBrZeVAiEnJargYPY"
    "pnYmB6TYGryF1IA0vCLjbYpsU0+0UI2mKgdJOJmTHoE+FR8qK10RISIGpGTB06JP4iILIX"
    "poKZn7k8q3Brew0XShVsNzTUQoggHuaqjO41Xn+qY6jwCO8pRNY20ctyCChiokOTI5jgSv"
    "FGEfgZmt6uVwj5K+3Gs4T9LDGGGriKJfOJRR0GvNVRS96JUp6VVbVNNPEGNTKhbrCLFREZ"
    "QJx80g3b7yi0JtnmsrQBW9MqGqtuNBKQRYxGD2iDXzFkRJFJq3dhMCrYCICGbAAFvAUp7+"
    "ntvt1wewkAKbKRhuxSXWFgw7O0AlJMM8qaRyREFAzHsDl83M11vLycVf+y2B5yX+UNgV0E"
    "jBFEnRSJH5k62RFjN1qxrpuUqnZKEdxefLUTXtSzXJjKvvBXb7sE85N3qt2VxJPTVz1FMz"
    "vtGHR1aAZsxtLaC7f2pFeZ7XarUVgMpumUTdxph2ooQD4fobzIogjbmVEukW3th7VBSHNW"
    "j6fqXEuZUVz/C/oL/OeKq6y9mlon6beVG3CtBaOXarEOAR0pqtIpM18CjlND3W6Y7Hz2r2"
    "8TNSH5iYayY26nlM7F4T6w0+yGv4bLT6lhL22t2GUpYTUOK1TQx3kvUttQEPyVeY7aKks7"
    "+3DKexok54HkWqOg9iWj90r/qxss6SutnmSkAdx8T85h3UyBPvN0Ktp3kvOJDsp4PseKwF"
    "fd63GtQwHNtea3OMuZbybxCfZnNMqh7xlH3HRqHza8ilnG+r6qtUperZRal6oiYF/pNy5V"
    "qp71BOgps/VtkgImE8Vac9PXWv0zFGvWIsHQebZ9L3IJ8pOQDd+ec+FMLLXcUSxSa2Wlpc"
    "3Ia91hK3y4/1Jd4Gw5OSUcc2oDDgmOOWGJf3/BA5nzncoMUKJiGXcj4/N7MD/a9/4G3wJA"
    "E2NkbVtFOE25J/ggj6HMzZ4RMdHLTzRrtxUW81Fmt4YclbusuPBO9gp/+lIHvZhlzKuWy3"
    "UvSQS6MARK97OQGer1rWzKtqZtThkhB/f+zd55bgUkA+ERHgs4kNflqxMOMvh4k1h6KMOn"
    "L49OGd3HX+iXO9+qN3GZeZ8gKX+95e5v8BlSUDOg=="
)
