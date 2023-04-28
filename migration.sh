max=31
for i in `seq 12 $max`
do
    echo "$i start"
    aws s3 mv "s3://unsw-cse-bronze-lake/brewai/sensors/2022-10-$i/" "s3://unsw-cse-bronze-lake/brewai/sensors/2022/10/$i/" --recursive
    echo "$i end"
done