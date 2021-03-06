import os
import argparse
import mars.dataframe as md
import pandas as pd
from run_io.db_adapter import convertDSNToRfc1738
from sqlalchemy import create_engine

import numpy as np
from PIL import Image
import tensorflow as tf
import torch
import numpy as np

import time

def build_argument_parser():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--dataset", type=str, required=False)
    parser.add_argument("--latency", type=float,required=False)
    parser.add_argument("--lag", type=int, required=False)
    return parser

# Inference
def detect(model,image_path,latency,lag,count,names=[]):

	# Images 
	img = Image.open(image_path)
	prediction = model(img, size=640)  # includes NMS'
	pred = prediction.pred[0]
	img = prediction.imgs[0]

	ans = {}
	if pred is not None:
		gn = torch.tensor(img.shape)[[1, 0, 1, 0]]  # normalization gain whwh
		time.sleep(latency)

		# Save results into files in the format of: class_index x y w h
		for *xyxy, conf, cls in reversed(pred):
			count += 1
			if count % lag == 0:
				cls = np.random.sample(names)
			# record the biggest confidence
			if cls not in ans.keys():
				ans[cls] = conf
			else:
				ans[cls] = max(conf,ans[cls])
	return ans


def inference():
	parser = build_argument_parser()
    args, _ = parser.parse_known_args()

    select_input = os.getenv("SQLFLOW_TO_RUN_SELECT")
    output = os.getenv("SQLFLOW_TO_RUN_INTO")
    output_tables = output.split(',')
    datasource = os.getenv("SQLFLOW_DATASOURCE")

    assert len(output_tables) == 1, "The output tables shouldn't be null and can contain only one."

    print("Connecting to database...")
    url = convertDSNToRfc1738(datasource, args.dataset)
    engine = create_engine(url)

    print("Printing result from SELECT statement as DataFrame...")
    input_md = md.read_sql(
        sql=select_input,
        con=engine)
    input_md.execute()
    print(input_md)

    image_dir = os.path.abspath('/opt/sqlflow/datasets/voc_simple/test/JPEGImages')
    input_md['filename'] = image_dir + "/" + input_md['filename'].astype(str)

    categories = ['person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', \
			'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', \
			'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', \
			'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', \
			'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', \
			'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', \
			'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', \
			'donut', 'cake', 'chair', 'couch', 'potted plant', 'bed', 'dining table', 'toilet', \
			'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone', 'microwave', 'oven', \
			'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair dryer','toothbrush']
    
    result_df = input_md.reindex(
        columns = ['image_id','filename'] + categories
    ).fillna(0).to_pandas()
    # do we really need to fill with 0? Can we left it empty as NaN?

    count = 0
    # Model
	model = torch.hub.load('ultralytics/yolov3', opt.base, pretrained=True).autoshape()  # for PIL/cv2/np inputs and NMS
    
    # model inference
    for row in result_df.itertuples():
        detected_objects = detect(model,row.filename,latency=args.latency,lag=args.lag,names=categories)
        for k,v in detected_objects.items():
            result_df.loc[row.Index, k] = v

    print("Persist the statement into the table {}".format(output_tables[0]))
    result_table = result_df.to_sql(
        name=output_tables[0],
        con=engine,
        index=False
    )

if __name__ == "__main__":
	'''
	Command:
	%%sqlflow
	DROP TABLE IF EXISTS voc.result;
	SELECT * FROM voc.annotations
	TO RUN hebafer/object-detection:latest
	CMD "yolov3_detect.py",
	    "--dataset=voc",
	    "--latency=0.05",
	    "--lag=100"
	INTO result;
	'''
    inference()