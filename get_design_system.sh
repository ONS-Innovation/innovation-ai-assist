#!/bin/sh

set -e

TMPFILE=`mktemp ./templates.XXXXXXXXXX`

wget https://github.com/ONSdigital/design-system/releases/download/70.0.4/templates.zip -O $TMPFILE
rm -rf ai_assist_builder/templates/components
rm -rf ai_assist_builder/templates/layout

unzip -d ./ai_assist_builder $TMPFILE
rm $TMPFILE