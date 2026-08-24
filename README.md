# Editor de PDF — Windows Portable v0.1.1 LAYOUT FIX

Aplicativo para montar, editar e gerar PDFs.

## Ajuste desta versão

- **Capa padrão:** entra inteira no PDF, sem cortar nenhuma parte, sem deformar e sem borda branca.
- A página da capa adapta a própria altura à proporção original da imagem.
- **Páginas internas:** usam a mesma largura padrão.
- A altura de cada página interna é calculada automaticamente conforme a proporção do conteúdo.
- A margem branca interna foi reduzida para aproximadamente **0,7 mm**.
- PDFs importados sem edição continuam sendo inseridos em formato vetorial sempre que possível.
- Páginas recortadas ou giradas são rasterizadas em alta qualidade.

## Funções

- adicionar imagens;
- adicionar PDFs com múltiplas páginas;
- recortar visualmente;
- girar;
- excluir e reorganizar páginas;
- capa padrão opcional;
- alterar/restaurar a capa padrão;
- gerar PDF final;
- Windows Portable sem instalação.

## Build manual no GitHub

O workflow está em:

`.github/workflows/build-windows.yml`

Vá em **Actions > Build Editor de PDF - Windows > Run workflow**.

O workflow não usa `actions/upload-artifact`; o ZIP é publicado diretamente em **Releases v0.1.1**, evitando o erro de quota de armazenamento de Artifacts.

Arquivo esperado no Release:

`Editor-de-PDF-Windows-Portable-v0.1.1.zip`
