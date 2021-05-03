import os
import argparse
import mars.dataframe as md
import pandas as pd
import MySQLdb
from run_io.db_adapter import convertDSNToRfc1738
from sqlalchemy import create_engine

import torch
import numpy as np


def build_argument_parser():
	parser = argparse.ArgumentParser(allow_abbrev=False)
	parser.add_argument("--dataset", type=str, required=False)
	return parser


if __name__ == "__main__":
	parser = build_argument_parser()
	args, _ = parser.parse_known_args()
	
	# First, run on your terminal:
	# docker run --name=sqlflow-mysql --rm -d -p 3306:3306 hebafer/sqlflow-mysql:1.0.0
	select_input = """
				SELECT * FROM coco.images
				ORDER BY images.id  ASC
				LIMIT 5
				"""
	output = "result"
	output_tables = output.split(',')
	datasource = "mysql://root:root@tcp(127.0.0.1:3306)/?maxAllowedPacket=0"
	args.dataset = "coco"

	print("Connecting to database...")
	url = convertDSNToRfc1738(datasource, args.dataset)
	engine = create_engine(url)

	# Delete table if exists
	db = MySQLdb.connect(
		host="0.0.0.0",
		user="root",
		password="root",
		database="coco"
	)
	cursor = db.cursor()
	sql = "DROP TABLE IF EXISTS result;"
	cursor.execute(sql)
	db.commit()

	print("Printing result from SELECT statement as DataFrame...")
	input_md = md.read_sql(
		sql=select_input,
		con=engine)
	input_md.execute()
	print(input_md)

	image_dir = os.path.abspath('../datasets/coco/test/test2017')
	input_md['file_name'] = image_dir + "/" + input_md['file_name'].astype(str)

	categories = ['person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
				'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
				'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe',
				'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard',
				'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
				'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl',
				'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza',
				'donut', 'cake', 'chair', 'couch', 'potted plant', 'bed', 'dining table', 'toilet',
				'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone', 'microwave', 'oven',
				'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair dryer', 'toothbrush']

	result_df = input_md.reindex(
		columns=['id', 'file_name'] + categories
	).fillna(0).to_pandas()

	# Collect Model
	model = torch.hub.load('ultralytics/yolov3', 'yolov3', verbose=False)

	# Retrieve Images
	imgs = result_df['file_name'].tolist()

	# Inference on all the images
	results = model(imgs[:])
	result_list = results.pandas().xyxy[:]

	# Iterate to collect confidence and class_names
	for i, value in enumerate(result_list):
		value = value.groupby(["name"], as_index=False).max()
		dict = pd.Series(value.confidence.values, index=value.name).to_dict()
		for k, v in dict.items():
			result_df.loc[i, k] = v

	print(result_df)
	print("Persist the statement into the table {}".format(output_tables[0]))
	result_table = result_df.to_sql(
		name=output_tables[0],
		con=engine,
		index=False
	)