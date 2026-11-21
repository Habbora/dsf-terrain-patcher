# X-Plane DSF Terrain Patcher

Edite o relevo de aeroportos e arredores aplicando patches OSM à malha DSF do X-Plane. As texturas do cenário são preservadas.

Foi testado no X-Plane 12. No X-Plane 11 não foi testado.

Serve para o DSF que já está no disco:

- photo ortho do X-Plane Map Enhancement
- photo ortho do Ortho4XP
- relevo baixado à parte
- malha original do X-Plane, apontando a pasta desse cenário

Se a pasta escolhida tiver `XPME_South_America`, esses são os tiles compilados.

## OSM e DSF

O **OSM** é o desenho. São polígonos no mapa, cada um com uma altitude em metros. Um polígono plano é uma área inteira na mesma altura. Uma rampa sobe de uma borda até a outra. O arquivo fica em `osm/` e termina em `.patch.osm`.

O **DSF** contém a malha de triângulos que o X-Plane desenha naquele grau de latitude e longitude. O programa lê esse arquivo, corta os triângulos no contorno do OSM e grava a altitude nos vértices.

A janela reúne a lista de OSM, a compilação, a recuperação do backup e o editor. O editor abre numa janela do próprio programa, com mapa, e só grava o arquivo. A compilação fica na janela principal.

## O que precisa

- Windows, Linux ou Mac
- No Windows pode usar o pacote `.exe` (sem instalar Python). Para desenvolver: Python 3.12
- 7-Zip no Linux e no Mac. No Windows ele já vem em `tools/win`
- O DSFTool 24-5, já em `tools/win`, `tools/lin` e `tools/mac`

### Windows com .exe (sem Python)

1. Extraia o ZIP inteiro para uma pasta em que você possa gravar arquivos.
2. Abra `DSFTerrainPatcher.exe` dentro da pasta extraída.

Os pacotes do release v0.1.0 foram publicados com o nome anterior, `OsmTerreno`.

Para gerar o pacote a partir do código-fonte, rode `Empacotar.bat` com Python 3.12 e compacte a pasta inteira `dist\DSFTerrainPatcher\`.

### Pacote Linux ou macOS

Extraia o arquivo `.tar.gz` e execute `./DSFTerrainPatcher` de dentro da pasta extraída. Instale o 7-Zip e deixe `7z` ou `7zz` disponível no PATH. No Linux, o editor empacotado usa Qt e requer uma sessão gráfica com as bibliotecas de sistema do Qt instaladas. No macOS, escolha `arm64` para Apple Silicon ou `x64` para Intel.

O workflow **Release** do GitHub Actions gera os pacotes em cada sistema. Uma execução manual disponibiliza os arquivos como artefatos. Uma tag `v*` publica os pacotes no GitHub Releases após a validação dos builds.

`DSFTerrainPatcher.bat` também abre o `.exe` se ele já existir em `dist\DSFTerrainPatcher\`.

### Desenvolver com Python

```
py -3.12 -m pip install -r requirements.txt
py -3.12 -m osmterreno
```

O código fica no pacote `osmterreno/`: `app.py` (janela), `compile_job.py` (compilação e recuperação), `mesh_cut.py` e `mesh_optimize.py` (corte e otimização da malha), `dsf_io.py` (DSF e 7z), `osm_patch.py` (leitura do OSM), `preview.py` (Ver malha) e `editor_launch.py`. O servidor do editor é `editor/server.py`.

## Abrir

No Windows, dê dois cliques em `DSFTerrainPatcher.bat` (ou no `.exe` empacotado). No Linux ou no Mac:

```
# Linux
chmod +x tools/lin/tools/DSFTool
# Mac
chmod +x tools/mac/tools/DSFTool
# Ambos
sh DSFTerrainPatcher.sh
```

Na primeira vez, use **Pasta...** e aponte para o cenário. No Map Enhancement é a pasta que contém `XPME_South_America`. No Ortho4XP ou na malha original, é a pasta daquele pacote. Esse caminho fica no `config.json`, só nesta máquina.

## Tutorial

1. Coloque os `.patch.osm` em `osm/`, ou use **Importar**. **Novo** cria um arquivo vazio.
2. Clique num OSM para selecionar. Ctrl seleciona vários e Shift seleciona um intervalo. **Selecionar tudo** e **Desmarcar tudo** valem para a lista inteira.
3. **Editar** abre o mapa do OSM selecionado. O satélite é só referência para desenhar. A altitude de cada polígono aparece na lista e no mapa. Salve com Ctrl+S. Compilar não fica nessa janela.

![Editor do OSM, com os polígonos de SBSP por cima da foto](docs/editor.png)

4. **Ver malha** mostra os triângulos do DSF na área do OSM, sem gravar nada. A segunda vez abre do cache, sem ler o DSF de novo. **Atual** é o arquivo do cenário, **Original** é o backup e **Gerar prévia** corta com a faixa e as opções que estão marcadas na janela, sem gravar o DSF. A linha vermelha é o polígono plano. A laranja é uma rampa. Verde é mais baixo, amarelo e laranja são mais altos. A roda aproxima, arrastar move, e o botão direito copia a coordenada.

![Triângulos do DSF e o contorno do OSM](docs/malha.png)
5. Ajuste a **Faixa ao redor**, em metros. **Otimizar malha** junta os triângulos planos. **Melhorar triângulos** reduz ângulos muito fechados. As duas são opcionais.
6. **Compilar** grava o DSF por cima do Map Enhancement. O backup `.antes_osm` é criado uma vez e não é substituído. **Recuperar** devolve esse backup.
7. Reinicie o X-Plane para ver o terreno. O registro da última compilação fica em `logs/Log.txt`.

![Janela do X-Plane DSF Terrain Patcher](docs/janela.png)

OSM do mesmo tile compilam juntos, a partir do backup. Um OSM não apaga o corte do outro. Vários tiles seguem um depois do outro.

## O que o corte faz

- Dentro do polígono, a altitude é a do OSM, mesmo abaixo do nível do mar.
- Na faixa ao redor, a altura desce lisa até o terreno.
- A malha no nível do mar, fora dos polígonos, não é reescrita. Isso evita o corte seco na água.
- O ponto na fronteira com um triângulo que não foi cortado fica na altura original, para não abrir fresta.
- O DSF volta compactado em 7z LZMA. LZMA2 faz o X-Plane recusar o arquivo.

O resumo dos manuais do DSFTool e do DDSTool está em `tools/MANUAL.md`.
