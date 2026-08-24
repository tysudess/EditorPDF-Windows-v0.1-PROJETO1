# Editor de PDF — v0.1

Primeira versão do aplicativo **Editor de PDF**, preparada para Windows e para build automático pelo GitHub Actions.

## Funções desta versão

- Adicionar imagens (PNG, JPG, JPEG, WEBP, BMP, TIFF)
- Adicionar PDFs com uma ou várias páginas
- Pré-visualização de páginas
- Miniaturas laterais
- Reordenar páginas por arrastar ou pelos botões de subir/descer
- Excluir páginas
- Girar páginas
- Recorte visual com o mouse
- Remover recorte
- Capa padrão **RADAR DE NOTÍCIAS — MÍDIA IMPRESSA** incluída no projeto
- Opção de incluir ou não a capa padrão como primeira página
- Trocar a capa padrão e salvar a escolha no modo portable
- Qualidade Alta (300 dpi), Média (220 dpi) ou Compacta (160 dpi) para páginas editadas
- Gerar PDF final
- Abrir a pasta após gerar

## Padrão do PDF

O programa foi configurado para seguir o padrão definido no projeto de capas:

- páginas em A4 automático, retrato ou paisagem conforme o conteúdo;
- proporção original preservada;
- margem mínima;
- nenhuma deformação da imagem;
- PDFs importados sem edição são inseridos preservando conteúdo vetorial sempre que possível;
- recortes e rotações são aplicados somente no PDF final — o arquivo original não é alterado.

## Build local no Windows

1. Instale Python 3.12.
2. Execute `build-windows.bat`.
3. O executável será criado em `dist/Editor-de-PDF.exe`.

## Build pelo GitHub Actions

O projeto já contém:

`.github/workflows/build-windows.yml`

Depois de enviar os arquivos para um repositório GitHub, abra **Actions > Build Editor de PDF - Windows > Run workflow**.

Ao terminar, baixe o artefato:

`Editor-de-PDF-Windows-Portable-v0.1`

O ZIP gerado contém o executável portable.
