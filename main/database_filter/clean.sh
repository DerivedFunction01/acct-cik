#!/bin/bash  
mv web_data.db web_data
mv prefiltered_data.db prefiltered_data

rm *.db
rm *.db-*
rm -rf analysis_output
rm *.log

mv web_data web_data.db
mv prefiltered_data prefiltered_data.db