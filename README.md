# Editor de PDF — Windows Portable v0.1

Aplicativo para montar e editar PDFs seguindo o padrão usado no projeto de capas de jornais.

## Funções

- adicionar imagens (PNG, JPG, JPEG, WEBP, BMP e TIFF);
- adicionar PDFs com uma ou várias páginas;
- pré-visualização e miniaturas;
- reorganizar e excluir páginas;
- girar páginas;
- recorte visual com o mouse;
- capa padrão **RADAR DE NOTÍCIAS — MÍDIA IMPRESSA**;
- incluir ou não a capa como primeira página;
- trocar a capa padrão;
- qualidade Alta, Média ou Compacta para páginas editadas;
- gerar o PDF final e abrir a pasta de destino.

## Padrão do PDF

- A4 automático em retrato ou paisagem conforme o conteúdo;
- proporção original preservada;
- margem mínima;
- sem esticar ou deformar imagens;
- PDFs sem edição preservam o conteúdo vetorial sempre que possível;
- recortes e rotações não alteram o arquivo original.

## Correção STORAGE-FIX

Este pacote corrige o erro do GitHub Actions:

`Failed to CreateArtifact: Artifact storage quota has been hit`

O workflow **não usa mais `actions/upload-artifact`**. O ZIP gerado é publicado diretamente em **GitHub Releases**, evitando a cota de armazenamento dos Artifacts.

O workflow também ficou somente manual (`workflow_dispatch`), para não executar um novo build a cada alteração no repositório.

## Como usar no GitHub

1. Substitua os arquivos do seu repositório pelos arquivos deste pacote, principalmente `.github/workflows/build-windows.yml`.
2. Entre na aba **Actions**.
3. Abra **Build Editor de PDF - Windows**.
4. Clique em **Run workflow**.
5. Depois de concluído, abra **Releases**.
6. Baixe `Editor-de-PDF-Windows-Portable-v0.1.zip` na Release `v0.1.0`.

## Build local no Windows

Se preferir gerar o executável no próprio computador, execute:

`build-windows.bat`

O executável será criado em:

`dist/Editor-de-PDF.exe`
